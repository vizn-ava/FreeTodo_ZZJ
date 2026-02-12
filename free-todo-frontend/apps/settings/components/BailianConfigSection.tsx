"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { useSaveConfig } from "@/lib/query";
import type { AppConfig } from "@/lib/query/config";
import { toastError, toastSuccess } from "@/lib/toast";
import { SettingsSection } from "./SettingsSection";

interface BailianConfigSectionProps {
	config: AppConfig | undefined;
	loading?: boolean;
}

function isMaskedApiKey(value: string): boolean {
	return value.includes("*");
}

export function BailianConfigSection({
	config,
	loading = false,
}: BailianConfigSectionProps) {
	const t = useTranslations("page.settings");
	const saveConfigMutation = useSaveConfig();

	const [apiKey, setApiKey] = useState((config?.bailianApiKey as string | undefined) ?? "");
	const [workspaceId, setWorkspaceId] = useState(
		(config?.bailianWorkspaceId as string | undefined) ?? "",
	);
	const [appId, setAppId] = useState((config?.bailianAppId as string | undefined) ?? "");

	const [initialApiKey, setInitialApiKey] = useState(apiKey);
	const [initialWorkspaceId, setInitialWorkspaceId] = useState(workspaceId);
	const [initialAppId, setInitialAppId] = useState(appId);

	const isSaving = loading || saveConfigMutation.isPending;

	useEffect(() => {
		if (!config) return;
		const nextApiKey = (config.bailianApiKey as string | undefined) ?? "";
		const nextWorkspaceId = (config.bailianWorkspaceId as string | undefined) ?? "";
		const nextAppId = (config.bailianAppId as string | undefined) ?? "";

		setApiKey(nextApiKey);
		setWorkspaceId(nextWorkspaceId);
		setAppId(nextAppId);
		setInitialApiKey(nextApiKey);
		setInitialWorkspaceId(nextWorkspaceId);
		setInitialAppId(nextAppId);
	}, [config]);

	const hasChanges = useMemo(
		() =>
			apiKey !== initialApiKey ||
			workspaceId !== initialWorkspaceId ||
			appId !== initialAppId,
		[apiKey, appId, initialApiKey, initialAppId, initialWorkspaceId, workspaceId],
	);

	const handleSave = async () => {
		if (!hasChanges) return;
		try {
			const payload: Record<string, string> = {
				bailianWorkspaceId: workspaceId.trim(),
				bailianAppId: appId.trim(),
			};

			// Only send API key when user actually enters a new key.
			const trimmedApiKey = apiKey.trim();
			if (trimmedApiKey && !isMaskedApiKey(trimmedApiKey)) {
				payload.bailianApiKey = trimmedApiKey;
			}

			await saveConfigMutation.mutateAsync({ data: payload });
			toastSuccess(t("bailianSaveSuccess"));

			setInitialApiKey(apiKey);
			setInitialWorkspaceId(workspaceId);
			setInitialAppId(appId);
		} catch (error) {
			console.error("保存百炼配置失败:", error);
			const errorMsg = error instanceof Error ? error.message : String(error);
			toastError(t("saveFailed", { error: errorMsg }));
		}
	};

	return (
		<SettingsSection
			title={t("bailianConfigTitle")}
			description={t("bailianConfigDescription")}
		>
			<div className="space-y-3">
				<div className="space-y-1">
					<label
						htmlFor="bailian-api-key"
						className="block text-sm font-medium text-foreground"
					>
						{t("apiKey")}
					</label>
					<input
						id="bailian-api-key"
						type="password"
						className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
						placeholder={t("bailianApiKeyPlaceholder")}
						value={apiKey}
						onFocus={() => {
							if (isMaskedApiKey(apiKey)) {
								setApiKey("");
							}
						}}
						onChange={(e) => setApiKey(e.target.value)}
						onBlur={() => void handleSave()}
						disabled={isSaving}
					/>
				</div>

				<div className="space-y-1">
					<label
						htmlFor="bailian-workspace-id"
						className="block text-sm font-medium text-foreground"
					>
						{t("bailianWorkspaceId")}
					</label>
					<input
						id="bailian-workspace-id"
						type="text"
						className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
						placeholder="llm-xxxxxxxxxxxx"
						value={workspaceId}
						onChange={(e) => setWorkspaceId(e.target.value)}
						onBlur={() => void handleSave()}
						disabled={isSaving}
					/>
				</div>

				<div className="space-y-1">
					<label
						htmlFor="bailian-app-id"
						className="block text-sm font-medium text-foreground"
					>
						{t("bailianAppId")}
					</label>
					<input
						id="bailian-app-id"
						type="text"
						className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
						placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
						value={appId}
						onChange={(e) => setAppId(e.target.value)}
						onBlur={() => void handleSave()}
						disabled={isSaving}
					/>
				</div>
			</div>
			<p className="mt-2 text-xs text-muted-foreground">{t("bailianConfigHint")}</p>
		</SettingsSection>
	);
}

