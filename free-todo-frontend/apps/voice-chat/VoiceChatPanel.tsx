"use client";

import { Mic, Phone, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelHeader } from "@/components/common/layout/PanelHeader";

type ChatMessage = {
	id: string;
	role: "user" | "assistant";
	text: string;
};

type SessionStatus = "idle" | "connecting" | "connected" | "ended" | "error";

type ProcessorRefs = {
	stream: MediaStream;
	audioContext: AudioContext;
	source: MediaStreamAudioSourceNode;
	processor: ScriptProcessorNode;
	muteGain: GainNode;
};
type BailianBootstrap = {
	workspace_id: string;
	app_id: string;
	model?: string;
};

const PCM_TARGET_SAMPLE_RATE = 16000;
const DOWNSTREAM_SAMPLE_RATE = 24000;

function downsampleTo16k(input: Float32Array, sourceRate: number): Int16Array {
	if (sourceRate === PCM_TARGET_SAMPLE_RATE) {
		const out = new Int16Array(input.length);
		for (let i = 0; i < input.length; i += 1) {
			const s = Math.max(-1, Math.min(1, input[i]));
			out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
		}
		return out;
	}

	const ratio = sourceRate / PCM_TARGET_SAMPLE_RATE;
	const outLength = Math.max(1, Math.floor(input.length / ratio));
	const out = new Int16Array(outLength);
	let offset = 0;
	for (let i = 0; i < outLength; i += 1) {
		const nextOffset = Math.min(input.length, Math.floor((i + 1) * ratio));
		let acc = 0;
		let count = 0;
		for (let j = offset; j < nextOffset; j += 1) {
			acc += input[j];
			count += 1;
		}
		const avg = count > 0 ? acc / count : 0;
		const s = Math.max(-1, Math.min(1, avg));
		out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
		offset = nextOffset;
	}
	return out;
}

function normalizeText(value: unknown): string {
	if (typeof value === "string") return value.trim();
	return "";
}

function pickEventText(payload: Record<string, unknown>): string {
	const direct = normalizeText(payload.text);
	if (direct) return direct;

	const output = payload.output;
	if (output && typeof output === "object") {
		const outputObj = output as Record<string, unknown>;
		const outputText = normalizeText(outputObj.text);
		if (outputText) return outputText;
	}

	return "";
}

export function VoiceChatPanel() {
	const t = useTranslations("voiceChat");
	const [status, setStatus] = useState<SessionStatus>("idle");
	const [error, setError] = useState<string | null>(null);
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const statusRef = useRef<SessionStatus>("idle");

	const socketRef = useRef<WebSocket | null>(null);
	const audioRef = useRef<ProcessorRefs | null>(null);
	const canSendAudioRef = useRef(false);
	const sessionTaskIdRef = useRef("");
	const userBufferRef = useRef("");
	const userMessageIdRef = useRef("");
	const assistantBufferRef = useRef("");
	const assistantMessageIdRef = useRef("");
	const playbackContextRef = useRef<AudioContext | null>(null);
	const playbackCursorRef = useRef(0);
	const activePlaybackRef = useRef<AudioBufferSourceNode[]>([]);
	const connectingTimeoutRef = useRef<number | null>(null);

	const pushMessage = useCallback((role: "user" | "assistant", text: string) => {
		const cleaned = text.trim();
		if (!cleaned) return;
		setMessages((prev) => [...prev, { id: crypto.randomUUID(), role, text: cleaned }]);
	}, []);

	const upsertMessage = useCallback(
		(messageId: string, role: "user" | "assistant", text: string) => {
			const cleaned = text.trim();
			if (!cleaned) return;
			setMessages((prev) => {
				const index = prev.findIndex((item) => item.id === messageId);
				if (index < 0) {
					return [...prev, { id: messageId, role, text: cleaned }];
				}
				const current = prev[index];
				if (current.role === role && current.text === cleaned) {
					return prev;
				}
				const next = [...prev];
				next[index] = { ...current, role, text: cleaned };
				return next;
			});
		},
		[],
	);

	const ensurePlaybackContext = useCallback(async () => {
		if (playbackContextRef.current) {
			if (playbackContextRef.current.state === "suspended") {
				await playbackContextRef.current.resume();
			}
			return playbackContextRef.current;
		}
		const context = new AudioContext({ sampleRate: DOWNSTREAM_SAMPLE_RATE });
		playbackContextRef.current = context;
		playbackCursorRef.current = context.currentTime;
		return context;
	}, []);

	const clearPlaybackQueue = useCallback(() => {
		for (const source of activePlaybackRef.current) {
			try {
				source.stop();
			} catch {}
		}
		activePlaybackRef.current = [];
		if (playbackContextRef.current) {
			playbackCursorRef.current = playbackContextRef.current.currentTime;
		}
	}, []);

	const playPcmChunk = useCallback(
		async (pcmBytes: ArrayBuffer) => {
			const context = await ensurePlaybackContext();
			const int16 = new Int16Array(pcmBytes);
			if (int16.length === 0) return;
			const float32 = new Float32Array(int16.length);
			for (let i = 0; i < int16.length; i += 1) {
				float32[i] = int16[i] / 0x8000;
			}

			const audioBuffer = context.createBuffer(1, float32.length, DOWNSTREAM_SAMPLE_RATE);
			audioBuffer.copyToChannel(float32, 0);

			const source = context.createBufferSource();
			source.buffer = audioBuffer;
			source.connect(context.destination);

			const startAt = Math.max(context.currentTime, playbackCursorRef.current);
			source.start(startAt);
			playbackCursorRef.current = startAt + audioBuffer.duration;
			activePlaybackRef.current.push(source);
			source.onended = () => {
				activePlaybackRef.current = activePlaybackRef.current.filter((item) => item !== source);
			};
		},
		[ensurePlaybackContext],
	);

	const stopAudioCapture = useCallback(() => {
		const refs = audioRef.current;
		if (!refs) return;
		refs.processor.disconnect();
		refs.source.disconnect();
		refs.muteGain.disconnect();
		for (const track of refs.stream.getTracks()) {
			track.stop();
		}
		void refs.audioContext.close();
		audioRef.current = null;
	}, []);

	const stopVoiceChat = useCallback(() => {
		canSendAudioRef.current = false;
		stopAudioCapture();
		clearPlaybackQueue();
		if (connectingTimeoutRef.current !== null) {
			window.clearTimeout(connectingTimeoutRef.current);
			connectingTimeoutRef.current = null;
		}
		const socket = socketRef.current;
		const taskId = sessionTaskIdRef.current;
		if (socket && socket.readyState === WebSocket.OPEN && taskId) {
			socket.send(
				JSON.stringify({
					header: { action: "run-task", task_id: taskId, streaming: "duplex" },
					payload: {
						input: { directive: "Stop" },
					},
				}),
			);
		}
		if (socket) {
			socket.close();
			socketRef.current = null;
		}
		if (playbackContextRef.current) {
			void playbackContextRef.current.close();
			playbackContextRef.current = null;
		}
		setStatus((prev) => (prev === "error" ? "error" : "ended"));
	}, [clearPlaybackQueue, stopAudioCapture]);

	const startAudioCapture = useCallback(async () => {
		const socket = socketRef.current;
		if (!socket || socket.readyState !== WebSocket.OPEN) return;

		const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
		const audioContext = new AudioContext();
		const source = audioContext.createMediaStreamSource(stream);
		const processor = audioContext.createScriptProcessor(4096, 1, 1);
		const muteGain = audioContext.createGain();
		muteGain.gain.value = 0;

		processor.onaudioprocess = (event) => {
			if (!canSendAudioRef.current) return;
			if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
			const input = event.inputBuffer.getChannelData(0);
			const pcm16 = downsampleTo16k(input, audioContext.sampleRate);
			socketRef.current.send(pcm16.buffer);
		};

		source.connect(processor);
		processor.connect(muteGain);
		muteGain.connect(audioContext.destination);

		audioRef.current = { stream, audioContext, source, processor, muteGain };
	}, []);

	const handleServerMessage = useCallback(
		(raw: MessageEvent<string>) => {
			try {
				const parsed = JSON.parse(raw.data) as Record<string, unknown>;
				const header = (parsed.header || {}) as Record<string, unknown>;
				const payload = (parsed.payload || {}) as Record<string, unknown>;
				const eventName = normalizeText(header.event);
				const eventNameLower = eventName.toLowerCase();
				const output = (payload.output || {}) as Record<string, unknown>;
				const outputEvent = normalizeText(output.event);
				const outputData = ((output.data as Record<string, unknown>) || {}) as Record<
					string,
					unknown
				>;

				if (eventName === "TaskFailed" || eventNameLower === "task-failed") {
					const message =
						normalizeText(payload.error_message) || t("errors.startFailed");
					setError(message);
					setStatus("error");
					return;
				}

				if (eventName === "TaskStarted" || eventNameLower === "task-started") {
					setStatus("connected");
					canSendAudioRef.current = true;
					if (connectingTimeoutRef.current !== null) {
						window.clearTimeout(connectingTimeoutRef.current);
						connectingTimeoutRef.current = null;
					}
					return;
				}

				// Bailian realtime app events are emitted via result-generated/output.event.
				if (eventNameLower === "result-generated" && outputEvent === "DialogStateChanged") {
					const state = normalizeText(output.state) || normalizeText(outputData.state);
					if (state === "Listening" || state === "ListeningInput") {
						setStatus("connected");
						canSendAudioRef.current = true;
						if (connectingTimeoutRef.current !== null) {
							window.clearTimeout(connectingTimeoutRef.current);
							connectingTimeoutRef.current = null;
						}
					}
					if (state === "Responding") {
						canSendAudioRef.current = false;
						userBufferRef.current = userBufferRef.current.trim();
						userMessageIdRef.current = "";
					}
					return;
				}

				if (eventNameLower === "result-generated" && outputEvent === "SpeechContent") {
					const text = pickEventText(outputData) || pickEventText(output);
					if (text) {
						// Barge-in: stop assistant playback as soon as user speech arrives.
						clearPlaybackQueue();
						userBufferRef.current = text.trim();
						if (!userBufferRef.current) return;
						if (!userMessageIdRef.current) {
							userMessageIdRef.current = crypto.randomUUID();
						}
						upsertMessage(userMessageIdRef.current, "user", userBufferRef.current);
					}
					return;
				}

				if (eventNameLower === "result-generated" && outputEvent === "RespondingContent") {
					const chunk = pickEventText(outputData) || pickEventText(output);
					if (chunk) {
						assistantBufferRef.current += chunk;
						if (!assistantMessageIdRef.current) {
							assistantMessageIdRef.current = crypto.randomUUID();
						}
						upsertMessage(
							assistantMessageIdRef.current,
							"assistant",
							assistantBufferRef.current,
						);
					}
					return;
				}

				if (eventNameLower === "result-generated" && outputEvent === "RespondingEnded") {
					const finalText = assistantBufferRef.current.trim();
					if (finalText) {
						const messageId = assistantMessageIdRef.current || crypto.randomUUID();
						upsertMessage(messageId, "assistant", finalText);
					}
					assistantBufferRef.current = "";
					assistantMessageIdRef.current = "";
					canSendAudioRef.current = true;
					return;
				}

				// Generic protocol fallback.
				if (eventName === "ResultGenerated") {
					const role = normalizeText(payload.role) === "user" ? "user" : "assistant";
					const text =
						pickEventText(payload) || pickEventText(outputData) || pickEventText(output);
					if (text) {
						pushMessage(role, text);
					}
					return;
				}

				if (eventName === "TaskFinished" || eventNameLower === "task-finished") {
					canSendAudioRef.current = false;
				}
			} catch (e) {
				console.error("Failed to parse Bailian message", e);
			}
		},
		[clearPlaybackQueue, pushMessage, t, upsertMessage],
	);

	const startVoiceChat = useCallback(async () => {
		setStatus("connecting");
		setError(null);
		setMessages([]);
		userBufferRef.current = "";
		userMessageIdRef.current = "";
		assistantBufferRef.current = "";
		assistantMessageIdRef.current = "";
		canSendAudioRef.current = false;
		sessionTaskIdRef.current = crypto.randomUUID();

		try {
			const bootstrapResponse = await fetch("/api/voice-chat/bailian/bootstrap");
			if (!bootstrapResponse.ok) {
				throw new Error(`bootstrap_${bootstrapResponse.status}`);
			}
			const bootstrap = (await bootstrapResponse.json()) as BailianBootstrap;

			const apiBase =
				process.env.NEXT_PUBLIC_API_URL ||
				`${window.location.protocol}//${window.location.hostname}:8100`;
			const wsBase = apiBase.replace(/^http/i, "ws");
			const ws = new WebSocket(`${wsBase}/api/voice-chat/bailian/ws`);
			socketRef.current = ws;

			ws.onmessage = (event) => {
				if (typeof event.data === "string") {
					handleServerMessage(event);
					return;
				}
				if (event.data instanceof Blob) {
					void event.data.arrayBuffer().then((buffer) => playPcmChunk(buffer));
					return;
				}
				if (event.data instanceof ArrayBuffer) {
					void playPcmChunk(event.data);
				}
			};

			ws.onerror = () => {
				setError(t("errors.startFailed"));
				setStatus("error");
			};

			ws.onclose = () => {
				stopAudioCapture();
				canSendAudioRef.current = false;
				if (status !== "error") {
					setStatus((prev) => (prev === "connecting" ? "error" : prev));
				}
			};

			await new Promise<void>((resolve, reject) => {
				const timeoutId = window.setTimeout(() => {
					reject(new Error("ws_connect_timeout"));
				}, 12000);

				const onOpen = async () => {
					try {
						await startAudioCapture();
						ws.send(
							JSON.stringify({
								header: {
									action: "run-task",
									task_id: sessionTaskIdRef.current,
									streaming: "duplex",
								},
								payload: {
									task_group: "aigc",
									task: "multimodal-generation",
									function: "generation",
									model: bootstrap.model || "multimodal-dialog",
									parameters: {
										upstream: {
											type: "AudioOnly",
											mode: "duplex",
											audio_format: "pcm",
											sample_rate: PCM_TARGET_SAMPLE_RATE,
										},
										downstream: {
											audio_format: "pcm",
											sample_rate: DOWNSTREAM_SAMPLE_RATE,
										},
										client_info: {
											user_id: "local-user",
											device: {
												name: "Chrome",
												version: "local",
											},
										},
									},
									input: {
										directive: "Start",
										workspaceId: bootstrap.workspace_id,
										appId: bootstrap.app_id,
									},
								},
							}),
						);
						window.clearTimeout(timeoutId);
						resolve();
					} catch (e) {
						window.clearTimeout(timeoutId);
						reject(e);
					}
				};

				const onError = () => {
					window.clearTimeout(timeoutId);
					reject(new Error("ws_open_failed"));
				};
				ws.addEventListener("open", onOpen, { once: true });
				ws.addEventListener("error", onError, { once: true });
			});

			// If backend handshake succeeds but protocol never enters Listening, fail fast.
			connectingTimeoutRef.current = window.setTimeout(() => {
				if (statusRef.current === "connecting") {
					setError(t("errors.startFailed"));
					setStatus("error");
					if (socketRef.current) {
						socketRef.current.close();
					}
				}
			}, 15000);
		} catch (startError) {
			console.error("Failed to start Bailian voice chat", startError);
			stopAudioCapture();
			setError(t("errors.startFailed"));
			setStatus("error");
		}
	}, [handleServerMessage, playPcmChunk, startAudioCapture, stopAudioCapture, t]);

	const toggleSession = useCallback(async () => {
		if (status === "connected" || status === "connecting") {
			stopVoiceChat();
			return;
		}
		await startVoiceChat();
	}, [startVoiceChat, status, stopVoiceChat]);

	useEffect(() => {
		statusRef.current = status;
	}, [status]);

	useEffect(() => {
		return () => {
			stopVoiceChat();
		};
	}, [stopVoiceChat]);

	const actionLabel = useMemo(() => {
		if (status === "connected" || status === "connecting") {
			return t("actions.endSession");
		}
		return t("actions.startSession");
	}, [status, t]);

	return (
		<div className="flex h-full flex-col bg-background">
			<PanelHeader icon={Phone} title={t("title")} />
			<div className="flex min-h-0 flex-1 flex-col px-4 pb-4 pt-3">
				<div className="relative min-h-0 flex-1 rounded-2xl border border-border bg-card/40 p-4">
					<div className="h-full overflow-auto space-y-3 pr-1">
						{messages.length === 0 ? (
							<div className="flex h-full items-center justify-center text-sm text-muted-foreground">
								{status === "connected"
									? t("status.listening")
									: status === "connecting"
										? t("status.connecting")
										: t("status.ready")}
							</div>
						) : (
							messages.map((message) => (
								<div
									key={message.id}
									className="rounded-xl border border-border/80 bg-background/80 px-3 py-2"
								>
									<div className="text-xs font-medium text-muted-foreground">
										{message.role === "user"
											? t("transcript.user")
											: t("transcript.assistant")}
									</div>
									<div className="mt-1 text-sm text-foreground">{message.text}</div>
								</div>
							))
						)}
					</div>
					{messages.length > 0 && status !== "ended" && status !== "error" && (
						<div className="pointer-events-none absolute inset-x-4 bottom-3 text-center text-xs text-muted-foreground">
							{status === "connected"
								? t("status.listening")
								: status === "connecting"
									? t("status.connecting")
									: t("status.ready")}
						</div>
					)}
				</div>

				{error && <div className="mt-2 text-xs text-destructive">{error}</div>}

				<div className="mt-4 flex justify-center">
					<button
						type="button"
						onClick={() => {
							void toggleSession();
						}}
						disabled={status === "connecting"}
						className="group relative inline-flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md transition hover:scale-105 disabled:cursor-not-allowed disabled:opacity-70"
						aria-label={actionLabel}
					>
						{status === "connected" && (
							<>
								<span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/35" />
								<span className="absolute inline-flex h-[86%] w-[86%] animate-pulse rounded-full border border-primary-foreground/40" />
							</>
						)}
						{status === "connected" ? (
							<Square className="relative h-6 w-6" />
						) : (
							<Mic className="relative h-6 w-6" />
						)}
					</button>
				</div>

				<div className="mt-2 text-center text-xs text-muted-foreground">{actionLabel}</div>
			</div>
		</div>
	);
}
