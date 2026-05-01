"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { signIn } from "next-auth/react";

import {
  IconAlert,
  IconCpu,
  IconMail,
  IconMenu,
  IconRetry,
  IconSend,
} from "@/components/ui/icons";
import type { ApiClient } from "@/lib/api";
import { createBrowserApiClient } from "@/lib/api";
import { formatPublishedAt, truncatePreview } from "@/lib/format";
import type { AgentStep, EmailMessage, EmailSummary, GmailStatus } from "@/lib/types";

interface MailDashboardProps {
  googleConfigured: boolean;
  apiClient?: ApiClient;
}

export function MailDashboard({ googleConfigured, apiClient: injectedApiClient }: MailDashboardProps) {
  const [apiClient] = useState(() => injectedApiClient ?? createBrowserApiClient());
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [messages, setMessages] = useState<EmailSummary[]>([]);
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [selectedMessage, setSelectedMessage] = useState<EmailMessage | null>(null);
  const [triageMarkdown, setTriageMarkdown] = useState("");
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingInbox, setLoadingInbox] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState(false);
  const [runningAgent, setRunningAgent] = useState(false);
  const [mobileInboxOpen, setMobileInboxOpen] = useState(false);

  const connected = gmailStatus?.connected ?? false;
  const selectedSummary = useMemo(
    () => messages.find((message) => message.uid === selectedUid) ?? null,
    [messages, selectedUid],
  );

  const refreshGmailStatus = useCallback(async () => {
    try {
      setGmailStatus(await apiClient.getGmailStatus());
    } catch {
      setGmailStatus({ connected: false, email: null, scopes: [] });
    }
  }, [apiClient]);

  const runTriage = useCallback(
    async (uid: string | null, options?: { limit?: number; unread_only?: boolean }) => {
      setRunningAgent(true);
      setNotice(null);
      try {
        const result = await apiClient.triageMail(
          uid
            ? { uid }
            : {
                limit: options?.limit ?? 1,
                unread_only: options?.unread_only ?? unreadOnly,
              },
        );
        setTriageMarkdown(result.triage_markdown);
        setAgentSteps(result.steps);
      } catch (cause) {
        setNotice(cause instanceof Error ? cause.message : "Unable to triage mail.");
      } finally {
        setRunningAgent(false);
      }
    },
    [apiClient, unreadOnly],
  );

  const selectMessage = useCallback(
    async (uid: string) => {
      setSelectedUid(uid);
      setMobileInboxOpen(false);
      setLoadingMessage(true);
      setNotice(null);
      try {
        const [message] = await Promise.all([
          apiClient.getMailMessage(uid),
          runTriage(uid),
        ]);
        setSelectedMessage(message);
      } catch (cause) {
        setNotice(cause instanceof Error ? cause.message : "Unable to open this email.");
      } finally {
        setLoadingMessage(false);
      }
    },
    [apiClient, runTriage],
  );

  const loadInbox = useCallback(
    async (nextUnreadOnly = unreadOnly) => {
      setLoadingInbox(true);
      setNotice(null);
      try {
        const inbox = await apiClient.listMailInbox({ limit: 20, unread_only: nextUnreadOnly });
        setMessages(inbox);
        if (inbox.length > 0) {
          await selectMessage(inbox[0].uid);
        } else {
          setSelectedUid(null);
          setSelectedMessage(null);
          await runTriage(null, { limit: 1, unread_only: nextUnreadOnly });
        }
      } catch (cause) {
        setNotice(cause instanceof Error ? cause.message : "Unable to load Gmail inbox.");
      } finally {
        setLoadingInbox(false);
      }
    },
    [apiClient, runTriage, selectMessage, unreadOnly],
  );

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      await refreshGmailStatus();
      if (cancelled) return;
      setLoadingInbox(false);
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [refreshGmailStatus]);

  useEffect(() => {
    if (!connected) return;
    void loadInbox(unreadOnly);
  }, [connected, loadInbox, unreadOnly]);

  const handleGoogleLogin = useCallback(() => {
    if (!googleConfigured) {
      setNotice("Google sign-in is not configured on this server.");
      return;
    }
    void signIn("google", { callbackUrl: "/mail" });
  }, [googleConfigured]);

  const handleAskAgent = useCallback(() => {
    const prompt = draft.trim();
    if (!prompt && !selectedUid) return;
    setDraft("");
    setNotice(prompt ? "Read-only mail agent refreshed the selected email." : null);
    void runTriage(selectedUid);
  }, [draft, runTriage, selectedUid]);

  return (
    <main className="grid h-screen min-h-0 grid-cols-1 bg-bg-thread text-text lg:grid-cols-[340px_minmax(0,1fr)_360px]">
      <InboxRail
        connected={connected}
        email={gmailStatus?.email ?? null}
        googleConfigured={googleConfigured}
        loading={loadingInbox}
        messages={messages}
        mobileOpen={mobileInboxOpen}
        selectedUid={selectedUid}
        unreadOnly={unreadOnly}
        onCloseMobile={() => setMobileInboxOpen(false)}
        onGoogleLogin={handleGoogleLogin}
        onRefresh={() => void loadInbox(unreadOnly)}
        onSelect={selectMessage}
        onUnreadOnlyChange={setUnreadOnly}
      />

      <section className="flex min-h-0 flex-col border-x border-line bg-bg-thread">
        <header className="flex items-center justify-between border-b border-line bg-bg-rail px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setMobileInboxOpen(true)}
            aria-label="Open inbox"
            className="om-icon-btn"
          >
            <IconMenu size={17} />
          </button>
          <div className="text-[13px] font-semibold">Mail Agent</div>
          <button
            type="button"
            aria-label="Refresh inbox"
            onClick={() => void loadInbox(unreadOnly)}
            className="om-icon-btn"
          >
            <IconRetry size={15} />
          </button>
        </header>

        {notice ? (
          <div className="mx-5 mt-4 flex items-start gap-2 rounded-md border border-warn-bd bg-warn-bg px-3 py-2.5 text-[12.5px] text-warn-fg">
            <IconAlert size={15} />
            <span>{notice}</span>
          </div>
        ) : null}

        <EmailReader
          loading={loadingMessage}
          message={selectedMessage}
          summary={selectedSummary}
          triageMarkdown={triageMarkdown}
        />

        <div className="shrink-0 border-t border-line bg-bg-rail px-4 py-3">
          <div className="rounded-lg border border-line-strong bg-bg-input p-3 shadow-soft">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleAskAgent();
                }
              }}
              placeholder="Ask about this email. The agent stays read-only."
              aria-label="Ask mail agent"
              rows={2}
              className="om-scroll block max-h-[130px] min-h-[54px] w-full resize-none border-0 bg-transparent text-[14px] leading-6 text-text outline-none placeholder:text-text-4"
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] text-text-4">
                <IconMail size={11} /> read-only Gmail agent
              </span>
              <button
                type="button"
                onClick={handleAskAgent}
                disabled={runningAgent || !connected}
                className="om-btn om-btn-send disabled:opacity-40"
              >
                Ask <IconSend size={13} />
              </button>
            </div>
          </div>
        </div>
      </section>

      <AgentInspector
        connected={connected}
        email={gmailStatus?.email ?? null}
        running={runningAgent}
        sourceUid={selectedUid}
        steps={agentSteps}
      />
    </main>
  );
}

function InboxRail({
  connected,
  email,
  googleConfigured,
  loading,
  messages,
  mobileOpen,
  selectedUid,
  unreadOnly,
  onCloseMobile,
  onGoogleLogin,
  onRefresh,
  onSelect,
  onUnreadOnlyChange,
}: {
  connected: boolean;
  email: string | null;
  googleConfigured: boolean;
  loading: boolean;
  messages: EmailSummary[];
  mobileOpen: boolean;
  selectedUid: string | null;
  unreadOnly: boolean;
  onCloseMobile: () => void;
  onGoogleLogin: () => void;
  onRefresh: () => void;
  onSelect: (uid: string) => void;
  onUnreadOnlyChange: (value: boolean) => void;
}) {
  return (
    <>
      {mobileOpen ? (
        <div className="fixed inset-0 z-20 bg-black/60 backdrop-blur-[2px] lg:hidden" onClick={onCloseMobile} />
      ) : null}
      <aside
        className={`om-scroll fixed inset-y-0 left-0 z-30 flex w-[min(360px,92vw)] flex-col overflow-y-auto border-r border-line bg-bg-rail transition-transform lg:static lg:z-auto lg:w-auto lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <header className="border-b border-line px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="om-meta">Gmail</div>
              <h1 className="mt-1 text-lg font-semibold tracking-tight">Mail Agent</h1>
            </div>
            <button type="button" onClick={onRefresh} aria-label="Refresh inbox" className="om-icon-btn">
              <IconRetry size={15} />
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <span className="grid h-7 w-7 place-items-center rounded-md border border-accent-ring bg-accent-soft text-accent-fg">
              <IconMail size={14} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-medium">
                {connected ? email ?? "Gmail connected" : "Gmail not connected"}
              </div>
              <div className="font-mono text-[10px] text-text-3">
                {connected ? "read-only inbox access" : "connect to read inbox"}
              </div>
            </div>
          </div>
          {!connected ? (
            <button
              type="button"
              onClick={onGoogleLogin}
              disabled={!googleConfigured}
              className="om-btn mt-3 w-full justify-center"
            >
              Sign in with Google
            </button>
          ) : (
            <div className="mt-3 grid grid-cols-2 gap-1 rounded-lg border border-line bg-bg-input p-1">
              <button
                type="button"
                onClick={() => onUnreadOnlyChange(true)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${
                  unreadOnly ? "bg-bg-emph text-text" : "text-text-3 hover:text-text"
                }`}
              >
                Unread
              </button>
              <button
                type="button"
                onClick={() => onUnreadOnlyChange(false)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${
                  !unreadOnly ? "bg-bg-emph text-text" : "text-text-3 hover:text-text"
                }`}
              >
                All inbox
              </button>
            </div>
          )}
        </header>

        <div className="flex-1">
          {loading ? (
            <div className="px-4 py-5 text-[12.5px] text-text-3">Loading inbox...</div>
          ) : messages.length === 0 ? (
            <div className="px-4 py-5 text-[12.5px] leading-6 text-text-3">
              {connected ? "No matching Gmail messages were returned." : "Connect Gmail to load messages."}
            </div>
          ) : (
            <ol>
              {messages.map((message) => (
                <li key={message.uid}>
                  <button
                    type="button"
                    onClick={() => onSelect(message.uid)}
                    className={`block w-full border-b border-line px-4 py-3 text-left transition-colors hover:bg-bg-raised ${
                      selectedUid === message.uid ? "bg-bg-emph" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-[13px] font-medium text-text">{message.from}</div>
                        <div className="mt-0.5 truncate text-[12.5px] text-text-2">{message.subject || "(no subject)"}</div>
                      </div>
                      {message.unread ? <span className="mt-1 h-2 w-2 rounded-full bg-accent-fg" /> : null}
                    </div>
                    <div className="mt-2 line-clamp-2 text-[12px] leading-5 text-text-3">
                      {truncatePreview(message.snippet, 118)}
                    </div>
                    <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-text-4">
                      <span>{formatPublishedAt(message.date)}</span>
                      <span>{message.has_attachments ? "attachment" : `UID ${message.uid}`}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </>
  );
}

function EmailReader({
  loading,
  message,
  summary,
  triageMarkdown,
}: {
  loading: boolean;
  message: EmailMessage | null;
  summary: EmailSummary | null;
  triageMarkdown: string;
}) {
  const active = message ?? summary;
  return (
    <div className="om-scroll min-h-0 flex-1 overflow-y-auto">
      {!active ? (
        <div className="flex h-full items-center justify-center px-6 text-center text-text-3">
          Select an inbox message to inspect its triage.
        </div>
      ) : (
        <div className="mx-auto max-w-4xl px-5 py-5">
          <div className="border-b border-line pb-4">
            <div className="om-meta">Selected message</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-text">
              {active.subject || "(no subject)"}
            </h2>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-text-3">
              <span>from {active.from}</span>
              <span>{formatPublishedAt(active.date)}</span>
              <span>{active.unread ? "unread" : "read"}</span>
              <span>UID {active.uid}</span>
            </div>
          </div>

          <section className="grid gap-5 py-5 xl:grid-cols-[minmax(0,1fr)_340px]">
            <article>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[13px] font-semibold text-text">Email body</h3>
                {loading ? <span className="font-mono text-[10px] text-text-4">loading...</span> : null}
              </div>
              <pre className="om-scroll max-h-[52vh] overflow-auto whitespace-pre-wrap rounded-md border border-line bg-bg-raised px-4 py-3 text-[13px] leading-6 text-text-2">
                {message?.body_text || active.snippet || "No readable body was returned."}
              </pre>
            </article>

            <aside>
              <div className="mb-2 flex items-center gap-2">
                <span className="grid h-6 w-6 place-items-center rounded-md border border-accent-ring bg-accent-soft text-accent-fg">
                  <IconCpu size={12} />
                </span>
                <h3 className="text-[13px] font-semibold text-text">Triage</h3>
              </div>
              <pre className="om-scroll max-h-[52vh] overflow-auto whitespace-pre-wrap rounded-md border border-line-strong bg-bg-input px-4 py-3 text-[12.5px] leading-6 text-text-2">
                {triageMarkdown || "Triage will appear here after the agent reads the message."}
              </pre>
            </aside>
          </section>
        </div>
      )}
    </div>
  );
}

function AgentInspector({
  connected,
  email,
  running,
  sourceUid,
  steps,
}: {
  connected: boolean;
  email: string | null;
  running: boolean;
  sourceUid: string | null;
  steps: AgentStep[];
}) {
  return (
    <aside className="hidden min-h-0 flex-col bg-bg-rail lg:flex">
      <header className="border-b border-line px-4 py-4">
        <div className="om-meta">Agent</div>
        <h2 className="mt-1 text-[14px] font-semibold">{running ? "Reading mail..." : "Read-only trace"}</h2>
        <div className="mt-2 text-[12px] text-text-3">
          {connected ? email ?? "Gmail connected" : "Gmail disconnected"}
        </div>
      </header>
      <div className="border-b border-line px-4 py-3">
        <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-text-2">
          <div className="rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <div className="text-[10px] uppercase tracking-wider text-text-4">Mode</div>
            <div className="mt-0.5 text-text">read-only</div>
          </div>
          <div className="rounded-md border border-line bg-bg-raised px-2.5 py-2">
            <div className="text-[10px] uppercase tracking-wider text-text-4">Source</div>
            <div className="mt-0.5 truncate text-text">{sourceUid ? `UID ${sourceUid}` : "none"}</div>
          </div>
        </div>
      </div>
      <div className="om-scroll min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {steps.length === 0 ? (
          <div className="rounded-md border border-dashed border-line-strong p-4 text-center text-[12px] leading-6 text-text-3">
            Tool calls appear here after the agent reads Gmail.
          </div>
        ) : (
          <ol className="relative ml-1.5 border-l border-line pl-4">
            {steps.map((step, index) => (
              <li key={`${step.tool_name}-${index}`} className="relative pb-4 last:pb-0">
                <span className="absolute -left-[22px] top-1.5 h-2 w-2 rounded-full bg-ok-fg" />
                <div className="text-[12.5px] font-medium text-text">Tool: {step.tool_name}</div>
                <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-text-4">
                  step {String(index + 1).padStart(2, "0")} - {step.status}
                </div>
                <pre className="mt-2 max-h-32 overflow-hidden rounded-md border border-line bg-bg-raised px-2 py-1.5 font-mono text-[10.5px] leading-5 text-text-3">
                  {JSON.stringify(step.arguments ?? {}, null, 2)}
                </pre>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
