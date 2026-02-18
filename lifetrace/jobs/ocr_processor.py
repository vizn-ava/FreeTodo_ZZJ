"""
OCR 处理器模块
包含 SimpleOCRProcessor 类和图像处理相关函数
"""

import hashlib
import os
import time

from lifetrace.storage import get_session, ocr_mgr, screenshot_mgr
from lifetrace.storage.models import OCRResult, Screenshot
from lifetrace.util.logging_config import get_logger
from lifetrace.util.settings import settings

from .ocr_config import (
    DEFAULT_IMAGE_MAX_SIZE,
    create_rapidocr_instance,
    get_ocr_config,
    setup_rapidocr_config,
)

logger = get_logger()

# 设置RapidOCR配置
setup_rapidocr_config()

try:
    import numpy as np
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR  # noqa: F401

    RAPIDOCR_AVAILABLE = True
except Exception as e:
    RAPIDOCR_AVAILABLE = False
    # Do NOT exit the whole backend process here.
    # OCR is an optional background capability; the API server should still start.
    logger.error(
        "RapidOCR 导入失败，OCR 功能将被禁用。请在当前 Python 环境中安装/修复: rapidocr-onnxruntime",
        exc_info=True,
    )
    logger.error(f"RapidOCR 导入异常信息: {e!r}")


def preprocess_image(image_path: str) -> "np.ndarray":
    """预处理图像，转换为RGB并缩放到合适大小

    Args:
        image_path: 图像文件路径

    Returns:
        预处理后的图像数组
    """
    if not RAPIDOCR_AVAILABLE:
        raise RuntimeError("RapidOCR 不可用：OCR 功能已禁用")
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail(DEFAULT_IMAGE_MAX_SIZE, Image.Resampling.LANCZOS)
        return np.array(img)


def extract_text_from_ocr_result(result, confidence_threshold: float = None) -> str:
    """从OCR结果中提取文本内容

    Args:
        result: OCR识别结果
        confidence_threshold: 置信度阈值，如果为None则从配置读取

    Returns:
        提取的文本内容
    """
    if confidence_threshold is None:
        confidence_threshold = settings.get("jobs.ocr.params.confidence_threshold")

    MIN_OCR_RESULT_FIELDS = 3

    ocr_text = ""
    if result:
        for item in result:
            if len(item) >= MIN_OCR_RESULT_FIELDS:
                text = item[1]
                confidence = float(item[2])
                if text and text.strip() and confidence > confidence_threshold:
                    ocr_text += text.strip() + "\n"

    return ocr_text


class SimpleOCRProcessor:
    """简化的OCR处理器类"""

    def __init__(self):
        self.ocr = None
        self.vector_service = None
        self.is_running = False

    def is_available(self):
        """检查OCR引擎是否可用"""
        return RAPIDOCR_AVAILABLE

    def start(self):
        """启动OCR处理服务"""
        self.is_running = True

    def stop(self):
        """停止OCR处理服务"""
        self.is_running = False

    def get_statistics(self):
        """获取OCR处理统计信息"""
        try:
            with get_session() as session:
                total_screenshots = session.query(Screenshot).count()
                ocr_results = session.query(OCRResult).count()
                unprocessed = total_screenshots - ocr_results

                return {
                    "status": "running" if self.is_running else "stopped",
                    "total_screenshots": total_screenshots,
                    "processed": ocr_results,
                    "unprocessed": unprocessed,
                    "interval": settings.get("jobs.ocr.interval"),
                }
        except Exception as e:
            logger.error(f"获取OCR统计信息失败: {e}")
            return {"status": "error", "error": str(e)}

    def _ensure_ocr_initialized(self):
        """确保OCR引擎已初始化"""
        if self.ocr is None:
            self.ocr = create_rapidocr_instance()

    def process_image(self, image_path):
        """处理单个图像文件"""
        try:
            self._ensure_ocr_initialized()

            start_time = time.time()
            img_array = preprocess_image(image_path)
            result, _ = self.ocr(img_array)
            processing_time = time.time() - start_time

            ocr_config = get_ocr_config()
            ocr_text = extract_text_from_ocr_result(result, ocr_config["confidence_threshold"])

            ocr_result = {
                "text_content": ocr_text,
                "confidence": ocr_config["default_confidence"],
                "language": ocr_config["language"],
                "processing_time": processing_time,
            }

            save_to_database(image_path, ocr_result, self.vector_service)

            return {
                "success": True,
                "text_content": ocr_text,
                "processing_time": processing_time,
            }

        except Exception as e:
            logger.error(f"处理图像失败: {e}")
            return {"success": False, "error": str(e)}


def save_to_database(image_path: str, ocr_result: dict, vector_service=None):
    """保存OCR结果到数据库"""
    try:
        screenshot = screenshot_mgr.get_screenshot_by_path(image_path)
        if not screenshot:
            logger.info(f"为外部截图文件创建数据库记录: {image_path}")
            screenshot_id = create_screenshot_record(image_path)
            if not screenshot_id:
                logger.warning(f"无法为外部文件创建截图记录: {image_path}")
                return
        else:
            screenshot_id = screenshot["id"]

        ocr_result_id = ocr_mgr.add_ocr_result(
            screenshot_id=screenshot_id,
            text_content=ocr_result["text_content"],
            confidence=ocr_result["confidence"],
            language=ocr_result.get("language", "ch"),
            processing_time=ocr_result["processing_time"],
        )

        screenshot_mgr.update_screenshot_processed(screenshot_id)

        if vector_service and vector_service.is_enabled() and ocr_result_id:
            _add_to_vector_database(ocr_result_id, screenshot_id, vector_service)

        # Best-effort: write OCR text to local markdown memory
        _write_ocr_to_md(image_path, ocr_result, screenshot_id)

    except Exception as e:
        logger.error(f"保存OCR结果到数据库失败: {e}")


def _write_ocr_to_md(image_path: str, ocr_result: dict, screenshot_id: int) -> None:
    """Best-effort write OCR result to local markdown memory."""
    try:
        from lifetrace.util.local_memory_writer import LocalMemoryWriter, MemoryRecord

        writer = LocalMemoryWriter()
        if not writer.is_enabled():
            return
        text_content = (ocr_result.get("text_content") or "").strip()
        if not text_content:
            return
        extra: dict[str, str] = {"screenshot_id": str(screenshot_id)}
        if ocr_result.get("language"):
            extra["language"] = ocr_result["language"]
        if ocr_result.get("confidence"):
            extra["confidence"] = f"{ocr_result['confidence']:.2f}"
        if ocr_result.get("processing_time"):
            extra["time"] = f"{ocr_result['processing_time']:.2f}s"
        filename = os.path.basename(image_path)
        writer.append_record(
            MemoryRecord(
                source="ocr",
                action="recognized",
                title=f"截图文字识别 ({filename})",
                content=text_content,
                extra=extra,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("OCR md write skipped: %s", exc)


def _add_to_vector_database(ocr_result_id: int, screenshot_id: int, vector_service):
    """将OCR结果添加到向量数据库"""
    try:
        with get_session() as session:
            ocr_obj = session.query(OCRResult).filter(OCRResult.id == ocr_result_id).first()
            screenshot_obj = (
                session.query(Screenshot).filter(Screenshot.id == screenshot_id).first()
            )

            if ocr_obj:
                success = vector_service.add_ocr_result(ocr_obj, screenshot_obj)
                if success:
                    logger.debug(f"OCR结果已添加到向量数据库: {ocr_result_id}")
                else:
                    logger.warning(f"向量数据库添加失败: {ocr_result_id}")

            if screenshot_obj and getattr(screenshot_obj, "event_id", None):
                try:
                    vector_service.upsert_event_document(screenshot_obj.event_id)
                except Exception:
                    pass
    except Exception as ve:
        logger.error(f"向量数据库操作失败: {ve}")


def create_screenshot_record(image_path: str):
    """为外部截图文件创建数据库记录"""
    try:
        if not os.path.exists(image_path):
            return None

        with open(image_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            with Image.open(image_path) as img:
                width, height = img.size
        except Exception:
            width, height = 0, 0

        filename = os.path.basename(image_path)
        app_name = "外部工具"
        window_title = filename

        if filename.startswith("Snipaste_"):
            app_name = "Snipaste"
            window_title = f"Snipaste截图 - {filename}"

        screenshot_id = screenshot_mgr.add_screenshot(
            file_path=image_path,
            file_hash=file_hash,
            width=width,
            height=height,
            metadata={
                "screen_id": 0,
                "app_name": app_name,
                "window_title": window_title,
            },
        )

        return screenshot_id

    except Exception as e:
        logger.error(f"创建外部截图记录失败: {e}")
        return None
