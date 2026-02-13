import type { RefObject } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type VoiceInputError = "unsupported" | "permission" | "upload" | "empty";

const SUPPORTED_MIME_TYPES = [
	"audio/webm;codecs=opus",
	"audio/webm",
	"audio/ogg;codecs=opus",
	"audio/ogg",
];

function pickSupportedMimeType() {
	if (typeof MediaRecorder === "undefined") return undefined;
	return SUPPORTED_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

type UseVoiceInputOptions = {
	onText: (text: string) => void;
	targetRef: RefObject<HTMLElement | null>;
	endpoint?: string;
	language?: string;
	hotkeyCode?: string;
	onStatusChange?: (status: "recording" | "transcribing" | null) => void;
};

export function useVoiceInput({
	onText,
	targetRef,
	endpoint = "/api/audio/transcriptions/quick",
	language,
	hotkeyCode = "AltRight",
	onStatusChange,
}: UseVoiceInputOptions) {
	const [isRecording, setIsRecording] = useState(false);
	const [isTranscribing, setIsTranscribing] = useState(false);
	const [error, setError] = useState<VoiceInputError | null>(null);

	const mediaRecorderRef = useRef<MediaRecorder | null>(null);
	const streamRef = useRef<MediaStream | null>(null);
	const chunksRef = useRef<Blob[]>([]);

	const mimeType = useMemo(() => pickSupportedMimeType(), []);

	const stopStreamTracks = useCallback(() => {
		if (!streamRef.current) return;
		for (const track of streamRef.current.getTracks()) {
			track.stop();
		}
		streamRef.current = null;
	}, []);

	const cleanup = useCallback(() => {
		if (mediaRecorderRef.current) {
			// Component unmount cleanup: stop recorder without uploading partial data.
			mediaRecorderRef.current.onstop = null;
			if (mediaRecorderRef.current.state !== "inactive") {
				mediaRecorderRef.current.stop();
			}
		}
		stopStreamTracks();
		mediaRecorderRef.current = null;
	}, [stopStreamTracks]);

	const uploadBlob = useCallback(
		async (blob: Blob) => {
			setIsTranscribing(true);
			onStatusChange?.("transcribing");
			setError(null);
			try {
				const requestTranscription = async (targetLanguage?: string) => {
					const formData = new FormData();
					const ext = blob.type.includes("ogg") ? "ogg" : "webm";
					const file = new File([blob], `voice.${ext}`, { type: blob.type });
					formData.append("file", file);
					const url = targetLanguage
						? `${endpoint}?language=${encodeURIComponent(targetLanguage)}`
						: endpoint;
					const response = await fetch(url, {
						method: "POST",
						body: formData,
					});
					if (!response.ok) {
						let detail = "";
						try {
							const payload = await response.json();
							detail = payload?.detail ? String(payload.detail) : "";
						} catch {
							detail = "";
						}
						throw new Error(
							detail ? `HTTP ${response.status}: ${detail}` : `HTTP ${response.status}`,
						);
					}
					return response.json();
				};

				const data = await requestTranscription(language);
				const toText = (payload: unknown) => {
					const segments = ((payload as { segments?: Array<{ text_content?: string; textContent?: string }> })?.segments || []);
					return segments
						.map((segment) => segment.textContent ?? segment.text_content ?? "")
						.filter(Boolean)
						.join(" ");
				};

				let text = toText(data);
				if (!text && language) {
					const retryData = await requestTranscription(undefined);
					text = toText(retryData);
				}
				if (!text) {
					setError("empty");
					return;
				}
				onText(text);
			} catch (err) {
				console.error(err);
				setError("upload");
			} finally {
				setIsTranscribing(false);
				onStatusChange?.(null);
			}
		},
		[endpoint, language, onText, onStatusChange],
	);

	const startRecording = useCallback(async () => {
		if (!navigator.mediaDevices?.getUserMedia) {
			setError("unsupported");
			return;
		}
		if (isTranscribing) return;
		try {
			const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
			streamRef.current = stream;
			chunksRef.current = [];
			const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
			mediaRecorderRef.current = recorder;

			recorder.ondataavailable = (event) => {
				if (event.data.size > 0) {
					chunksRef.current.push(event.data);
				}
			};

			recorder.onstop = () => {
				stopStreamTracks();
				const blob = new Blob(chunksRef.current, {
					type: recorder.mimeType || "audio/webm",
				});
				chunksRef.current = [];
				if (blob.size === 0) {
					setError("empty");
					setIsRecording(false);
					onStatusChange?.(null);
					mediaRecorderRef.current = null;
					return;
				}
				mediaRecorderRef.current = null;
				void uploadBlob(blob);
			};

			recorder.start(250);
			setIsRecording(true);
			onStatusChange?.("recording");
		} catch (err) {
			console.error(err);
			setError("permission");
			cleanup();
		}
	}, [cleanup, isTranscribing, mimeType, uploadBlob, onStatusChange, stopStreamTracks]);

	const stopRecording = useCallback(() => {
		const recorder = mediaRecorderRef.current;
		if (!recorder) return;
		setIsRecording(false);
		onStatusChange?.(null);
		if (recorder.state !== "inactive") {
			try {
				recorder.requestData();
			} catch {
				// ignore
			}
			recorder.stop();
		} else {
			stopStreamTracks();
			mediaRecorderRef.current = null;
		}
	}, [onStatusChange, stopStreamTracks]);

	const toggleRecording = useCallback(() => {
		if (isRecording) {
			stopRecording();
		} else {
			void startRecording();
		}
	}, [isRecording, startRecording, stopRecording]);

	useEffect(() => {
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.code !== hotkeyCode) return;
			if (event.repeat) return;
			if (!targetRef.current) return;
			if (document.activeElement !== targetRef.current) return;
			event.preventDefault();
			void startRecording();
		};

		const handleKeyUp = (event: KeyboardEvent) => {
			if (event.code !== hotkeyCode) return;
			if (!targetRef.current) return;
			if (document.activeElement !== targetRef.current) return;
			event.preventDefault();
			stopRecording();
		};

		window.addEventListener("keydown", handleKeyDown);
		window.addEventListener("keyup", handleKeyUp);
		return () => {
			window.removeEventListener("keydown", handleKeyDown);
			window.removeEventListener("keyup", handleKeyUp);
		};
	}, [targetRef, startRecording, stopRecording, hotkeyCode]);

	useEffect(() => cleanup, [cleanup]);

	return {
		isRecording,
		isTranscribing,
		error,
		startRecording,
		stopRecording,
		toggleRecording,
		clearError: () => setError(null),
	};
}
