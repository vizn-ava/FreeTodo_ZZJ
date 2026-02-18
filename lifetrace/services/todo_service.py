"""Todo 业务逻辑层

处理 Todo 相关的业务逻辑，与数据访问层解耦。
"""

from typing import Any

from fastapi import HTTPException

from lifetrace.repositories.interfaces import ITodoRepository
from lifetrace.schemas.todo import TodoCreate, TodoResponse, TodoUpdate
from lifetrace.util.local_memory_writer import LocalMemoryWriter, MemoryRecord
from lifetrace.util.logging_config import get_logger

logger = get_logger()


class TodoService:
    """Todo 业务逻辑层"""

    def __init__(self, repository: ITodoRepository):
        self.repository = repository
        self._memory_writer = LocalMemoryWriter()

    def _write_todo_to_md(self, todo: TodoResponse, action: str) -> None:
        """Best-effort write todo event to local markdown memory."""
        try:
            if not self._memory_writer.is_enabled():
                return
            extra: dict[str, str] = {"id": str(todo.id), "status": todo.status}
            if todo.priority and todo.priority != "none":
                extra["priority"] = todo.priority
            if todo.deadline:
                extra["deadline"] = todo.deadline.strftime("%Y-%m-%d %H:%M")
            if todo.tags:
                extra["tags"] = ", ".join(todo.tags)

            parts: list[str] = []
            if todo.description:
                parts.append(todo.description)
            if todo.user_notes:
                parts.append(f"备注: {todo.user_notes}")

            self._memory_writer.append_record(
                MemoryRecord(
                    source="todo",
                    action=action,
                    title=todo.name,
                    content="\n".join(parts) if parts else "",
                    extra=extra,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Todo md write skipped: %s", exc)

    def get_todo(self, todo_id: int) -> TodoResponse:
        """获取单个 Todo"""
        todo = self.repository.get_by_id(todo_id)
        if not todo:
            raise HTTPException(status_code=404, detail="todo 不存在")
        return TodoResponse(**todo)

    def list_todos(self, limit: int, offset: int, status: str | None) -> dict[str, Any]:
        """获取 Todo 列表"""
        todos = self.repository.list_todos(limit, offset, status)
        total = self.repository.count(status)
        return {"total": total, "todos": [TodoResponse(**t) for t in todos]}

    def create_todo(self, data: TodoCreate) -> TodoResponse:
        """创建 Todo"""
        todo_id = self.repository.create(
            name=data.name,
            description=data.description,
            user_notes=data.user_notes,
            parent_todo_id=data.parent_todo_id,
            deadline=data.deadline,
            start_time=data.start_time,
            status=data.status.value if data.status else "active",
            priority=data.priority.value if data.priority else "none",
            order=data.order,
            tags=data.tags,
            related_activities=data.related_activities,
        )
        if not todo_id:
            raise HTTPException(status_code=500, detail="创建 todo 失败")

        todo = self.get_todo(todo_id)
        self._write_todo_to_md(todo, "created")
        return todo

    def update_todo(self, todo_id: int, data: TodoUpdate) -> TodoResponse:
        """更新 Todo"""
        # 检查是否存在
        if not self.repository.get_by_id(todo_id):
            raise HTTPException(status_code=404, detail="todo 不存在")

        # 提取有效字段（只更新请求中携带的字段）
        fields_set = (
            getattr(data, "model_fields_set", None)
            or getattr(data, "__fields_set__", None)
            or set()
        )
        kwargs = {field: getattr(data, field) for field in fields_set}

        # 枚举转字符串
        if "status" in kwargs and kwargs["status"] is not None:
            kwargs["status"] = kwargs["status"].value
        if "priority" in kwargs and kwargs["priority"] is not None:
            kwargs["priority"] = kwargs["priority"].value

        if not self.repository.update(todo_id, **kwargs):
            raise HTTPException(status_code=500, detail="更新 todo 失败")

        todo = self.get_todo(todo_id)
        # Determine action: status change is more specific
        action = "updated"
        if "status" in kwargs:
            status_val = kwargs["status"]
            if status_val == "completed":
                action = "completed"
            elif status_val == "canceled":
                action = "canceled"
        self._write_todo_to_md(todo, action)
        return todo

    def delete_todo(self, todo_id: int) -> None:
        """删除 Todo"""
        todo_data = self.repository.get_by_id(todo_id)
        if not todo_data:
            raise HTTPException(status_code=404, detail="todo 不存在")
        # Write to md before deleting
        try:
            self._write_todo_to_md(TodoResponse(**todo_data), "deleted")
        except Exception:  # noqa: BLE001
            pass
        if not self.repository.delete(todo_id):
            raise HTTPException(status_code=500, detail="删除 todo 失败")

    def reorder_todos(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """批量重排序 Todo"""
        if not self.repository.reorder(items):
            raise HTTPException(status_code=500, detail="批量重排序失败")
        return {"success": True, "message": f"成功更新 {len(items)} 个待办的排序"}
