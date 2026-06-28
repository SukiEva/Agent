<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import {
  applyAgUiEvent,
  createRuntimeState,
  resetRuntimeState,
  updateToolCall,
  type AgUiEvent,
  type ToolCall,
} from "./runtime/events";

type Capability = {
  agent_id: string;
  label: string;
  description: string;
  available: boolean;
};

type Conversation = {
  conversation_id: string;
  client_id: string;
};

type AttachmentRef = {
  file_id: string;
  name: string;
  mime_type?: string | null;
  size_bytes?: number | null;
};

const apiBase = import.meta.env.VITE_AGENT_SERVER_URL ?? "http://localhost:8000";

const conversation = ref<Conversation | null>(null);
const capabilities = ref<Capability[]>([]);
const selectedAgentId = ref("");
const input = ref("run demo task");
const bridgeEnabled = ref(false);
const status = ref("disconnected");
const runtimeState = reactive(createRuntimeState());
const attachments = ref<AttachmentRef[]>([]);

let source: EventSource | null = null;

const canRun = computed(() => conversation.value && input.value.trim() && !runtimeState.isRunning);

onMounted(async () => {
  await bootstrap();
});

onBeforeUnmount(() => {
  source?.close();
});

async function bootstrap() {
  try {
    conversation.value = await post<Conversation>("/api/conversations", {});
    await loadCapabilities();
    connectEvents();
  } catch (unknownError) {
    runtimeState.error = errorMessage(unknownError);
  }
}

async function loadCapabilities() {
  capabilities.value = await get<Capability[]>("/api/capabilities");
  selectedAgentId.value = capabilities.value.find((capability) => capability.available)?.agent_id ?? "";
}

function connectEvents() {
  if (!conversation.value) return;
  source?.close();
  status.value = "connecting";
  source = new EventSource(`${apiBase}/api/conversations/${conversation.value.conversation_id}/events`);
  source.onopen = () => {
    status.value = "connected";
  };
  source.onerror = () => {
    status.value = "reconnecting";
  };
  source.onmessage = (event) => {
    handleEvent(JSON.parse(event.data) as AgUiEvent);
  };
}

async function startRun() {
  if (!conversation.value || !canRun.value) return;
  resetRuntimeState(runtimeState);
  runtimeState.isRunning = true;
  const response = await post<{ run_id: string; root_task_id: string }>("/api/runs", {
    conversation_id: conversation.value.conversation_id,
    client_id: conversation.value.client_id,
    message: {
      type: "text",
      content: input.value,
    },
    selected_agent_id: selectedAgentId.value || null,
    attachments: attachments.value,
    context: bridgeEnabled.value
      ? {
          bridge: {
            enabled: true,
            action_name: "get_selected_text",
            timeout_ms: 30000,
          },
        }
      : {},
  });
  runtimeState.runId = response.run_id;
}

async function uploadAttachment(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  runtimeState.error = null;
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${apiBase}/api/files`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error(await response.text());
    attachments.value.push((await response.json()) as AttachmentRef);
  } catch (unknownError) {
    runtimeState.error = errorMessage(unknownError);
  } finally {
    input.value = "";
  }
}

function removeAttachment(fileId: string) {
  attachments.value = attachments.value.filter((attachment) => attachment.file_id !== fileId);
}

async function cancelRun() {
  if (!runtimeState.runId) return;
  await post(`/api/runs/${runtimeState.runId}/cancel`, {});
  runtimeState.isRunning = false;
}

function handleEvent(event: AgUiEvent) {
  const effect = applyAgUiEvent(runtimeState, event);
  if (effect.executeToolCallId) void executeToolCall(effect.executeToolCallId);
}

async function executeToolCall(toolCallId: string) {
  const toolCall = runtimeState.toolCalls.find((item) => item.id === toolCallId);
  if (!toolCall) return;
  updateToolCall(runtimeState, toolCallId, { status: "running" });
  try {
    const result = await executeBridgeTool(toolCall);
    await post(`/api/client-actions/${toolCallId}/result`, {
      status: "completed",
      result,
    });
  } catch (unknownError) {
    updateToolCall(runtimeState, toolCallId, { status: "failed" });
    await post(`/api/client-actions/${toolCallId}/result`, {
      status: "failed",
      result: {},
      error: {
        code: "CLIENT_TOOL_FAILED",
        message: errorMessage(unknownError),
        recoverable: true,
        retryable: false,
      },
    });
  }
}

async function executeBridgeTool(toolCall: ToolCall): Promise<Record<string, unknown>> {
  if (toolCall.name === "get_selected_text") {
    return {
      text: window.getSelection()?.toString() ?? "",
    };
  }
  if (toolCall.name === "get_current_url") {
    return {
      url: window.location.href,
    };
  }
  throw new Error(`Unsupported bridge tool: ${toolCall.name}`);
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`);
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

function errorMessage(unknownError: unknown): string {
  return unknownError instanceof Error ? unknownError.message : String(unknownError);
}
</script>

<template>
  <main class="app-shell">
    <section class="workspace">
      <aside class="sidebar">
        <div class="brand">
          <span class="brand-mark">A</span>
          <div>
            <h1>Agent Runtime</h1>
            <p>{{ status }}</p>
          </div>
        </div>

        <label class="field">
          <span>Business agent</span>
          <select v-model="selectedAgentId">
            <option v-for="capability in capabilities" :key="capability.agent_id" :value="capability.agent_id">
              {{ capability.label }}
            </option>
          </select>
        </label>

        <div class="capability-list">
          <article v-for="capability in capabilities" :key="capability.agent_id" class="capability">
            <strong>{{ capability.label }}</strong>
            <span>{{ capability.available ? "available" : "unavailable" }}</span>
            <p>{{ capability.description }}</p>
          </article>
        </div>
      </aside>

      <section class="main-pane">
        <div class="composer">
          <textarea v-model="input" rows="4" />
          <div class="attachments">
            <label class="file-button">
              <input type="file" @change="uploadAttachment" />
              <span>Add file</span>
            </label>
            <div v-for="attachment in attachments" :key="attachment.file_id" class="attachment">
              <span>{{ attachment.name }}</span>
              <small>{{ attachment.size_bytes ?? 0 }} bytes</small>
              <button type="button" class="icon-button" @click="removeAttachment(attachment.file_id)">x</button>
            </div>
          </div>
          <div class="composer-actions">
            <label class="toggle">
              <input v-model="bridgeEnabled" type="checkbox" />
              <span>Bridge tool</span>
            </label>
            <button :disabled="!canRun" @click="startRun">Run</button>
            <button class="secondary" :disabled="!runtimeState.isRunning" @click="cancelRun">Stop</button>
          </div>
        </div>

        <p v-if="runtimeState.error" class="error">{{ runtimeState.error }}</p>

        <section class="stream">
          <div class="panel">
            <h2>Progress</h2>
            <ol>
              <li v-for="(progress, index) in runtimeState.progressEvents" :key="`${progress.agentId}-${index}`">
                <span>{{ progress.agentId }}</span>
                {{ progress.message }}
              </li>
            </ol>
          </div>

          <div class="panel">
            <h2>Messages</h2>
            <article v-for="message in runtimeState.messages" :key="message.id" class="message">
              <span>{{ message.role }}</span>
              <p>{{ message.content }}</p>
            </article>
          </div>

          <div class="panel">
            <h2>Bridge</h2>
            <article v-for="toolCall in runtimeState.toolCalls" :key="toolCall.id" class="tool-call">
              <strong>{{ toolCall.name }}</strong>
              <span>{{ toolCall.status }}</span>
              <code>{{ toolCall.id }}</code>
            </article>
          </div>

          <div class="panel">
            <h2>UI</h2>
            <article v-for="(render, index) in runtimeState.uiRenders" :key="`${render.component}-${index}`" class="result-card">
              <template v-if="render.component === 'demo.result_card'">
                <strong>{{ render.props.title }}</strong>
                <p>{{ render.props.summary }}</p>
                <ul>
                  <li v-for="item in (render.props.items as string[])" :key="item">{{ item }}</li>
                </ul>
                <div v-if="render.props.attachments?.length" class="attachment-summary">
                  <span>Attachments</span>
                  <ul>
                    <li v-for="attachment in render.props.attachments" :key="attachment.file_id">
                      {{ attachment.name }} <small>{{ attachment.file_id }}</small>
                    </li>
                  </ul>
                </div>
              </template>
              <template v-else>
                <strong>{{ render.fallback?.component ?? render.component }}</strong>
                <p>{{ render.fallback?.props?.content ?? "Unsupported component" }}</p>
              </template>
            </article>
          </div>
        </section>
      </section>
    </section>
  </main>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f6f7f9;
  color: #17202a;
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar {
  border-right: 1px solid #d9dee5;
  background: #ffffff;
  padding: 24px;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 28px;
}

.brand-mark {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 8px;
  background: #1c6b5c;
  color: #ffffff;
  font-weight: 700;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  font-size: 18px;
}

h2 {
  font-size: 14px;
  margin-bottom: 12px;
}

.brand p,
.capability span,
.message span,
.tool-call span,
.field span {
  color: #687385;
  font-size: 12px;
}

.field {
  display: grid;
  gap: 8px;
  margin-bottom: 20px;
}

select,
textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #cbd3dd;
  border-radius: 8px;
  background: #ffffff;
  color: inherit;
  font: inherit;
}

select {
  height: 38px;
  padding: 0 10px;
}

textarea {
  resize: vertical;
  min-height: 110px;
  padding: 12px;
}

.capability-list {
  display: grid;
  gap: 10px;
}

.capability,
.panel,
.composer {
  border: 1px solid #d9dee5;
  border-radius: 8px;
  background: #ffffff;
}

.capability {
  padding: 12px;
}

.capability p {
  margin-top: 8px;
  color: #4c5969;
  font-size: 13px;
  line-height: 1.45;
}

.main-pane {
  padding: 24px;
}

.composer {
  padding: 16px;
}

.composer-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
  margin-top: 12px;
}

.attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.file-button {
  display: inline-flex;
  height: 30px;
  align-items: center;
  border: 1px solid #cbd3dd;
  border-radius: 8px;
  padding: 0 10px;
  background: #f8fafc;
  color: #344253;
  cursor: pointer;
  font-size: 13px;
}

.file-button input {
  display: none;
}

.attachment {
  display: inline-grid;
  grid-template-columns: auto auto 24px;
  gap: 8px;
  align-items: center;
  min-height: 30px;
  border: 1px solid #d9dee5;
  border-radius: 8px;
  padding: 0 4px 0 10px;
  background: #ffffff;
  font-size: 13px;
}

.attachment small {
  color: #687385;
}

.toggle {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  margin-right: auto;
  color: #4c5969;
  font-size: 13px;
}

button {
  height: 36px;
  border: 0;
  border-radius: 8px;
  padding: 0 16px;
  background: #1c6b5c;
  color: #ffffff;
  font-weight: 650;
  cursor: pointer;
}

button.secondary {
  background: #dfe5ec;
  color: #17202a;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.icon-button {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  padding: 0;
  background: #edf0f4;
  color: #344253;
}

.error {
  margin-top: 12px;
  color: #9b1c31;
}

.stream {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.panel {
  min-height: 160px;
  padding: 16px;
}

ol,
ul {
  margin: 0;
  padding-left: 18px;
}

li {
  margin: 8px 0;
}

li span {
  display: block;
  color: #687385;
  font-size: 12px;
}

.message,
.tool-call,
.result-card {
  border-top: 1px solid #edf0f4;
  padding: 12px 0;
}

.message:first-of-type,
.tool-call:first-of-type,
.result-card:first-of-type {
  border-top: 0;
}

.message p,
.result-card p {
  margin-top: 6px;
  line-height: 1.55;
}

.attachment-summary {
  margin-top: 10px;
}

.attachment-summary ul {
  padding-left: 18px;
}

.attachment-summary small {
  color: #687385;
  font-size: 11px;
}

.tool-call {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 10px;
}

.tool-call code {
  grid-column: 1 / -1;
  overflow: hidden;
  color: #687385;
  font-size: 12px;
  text-overflow: ellipsis;
}

@media (max-width: 860px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .sidebar {
    border-right: 0;
    border-bottom: 1px solid #d9dee5;
  }

  .stream {
    grid-template-columns: 1fr;
  }
}
</style>
