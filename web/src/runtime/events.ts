export type AgUiEvent = {
  type: string;
  [key: string]: unknown;
};

export type Message = {
  id: string;
  role: string;
  content: string;
  complete: boolean;
};

export type ProgressEvent = {
  agentId: string;
  runId: string;
  taskId: string;
  message: string;
  status: "running" | "completed";
};

export type ToolCall = {
  id: string;
  name: string;
  args: string;
  status: "pending" | "running" | "completed" | "failed";
};

export type UiRender = {
  component: string;
  component_version: string;
  props: Record<string, unknown> & {
    attachments?: AttachmentSummary[];
  };
  fallback?: {
    component: string;
    props: Record<string, unknown>;
  };
};

export type AttachmentSummary = {
  file_id: string;
  name: string;
  mime_type?: string | null;
  size_bytes?: number | null;
};

export type RuntimeState = {
  isRunning: boolean;
  runId: string | null;
  messages: Message[];
  progressEvents: ProgressEvent[];
  toolCalls: ToolCall[];
  uiRenders: UiRender[];
  error: string | null;
};

export type RuntimeEffect = {
  executeToolCallId?: string;
};

export function createRuntimeState(): RuntimeState {
  return {
    isRunning: false,
    runId: null,
    messages: [],
    progressEvents: [],
    toolCalls: [],
    uiRenders: [],
    error: null,
  };
}

export function resetRuntimeState(state: RuntimeState): void {
  state.isRunning = false;
  state.runId = null;
  state.messages.splice(0);
  state.progressEvents.splice(0);
  state.toolCalls.splice(0);
  state.uiRenders.splice(0);
  state.error = null;
}

export function applyAgUiEvent(state: RuntimeState, event: AgUiEvent): RuntimeEffect {
  switch (event.type) {
    case "RUN_STARTED":
      state.isRunning = true;
      state.runId = String(event.runId);
      return {};
    case "RUN_FINISHED":
      state.isRunning = false;
      return {};
    case "RUN_ERROR":
      state.isRunning = false;
      state.error = String(event.message ?? "Run failed");
      return {};
    case "TEXT_MESSAGE_START":
      state.messages.push({
        id: String(event.messageId),
        role: String(event.role ?? "assistant"),
        content: "",
        complete: false,
      });
      return {};
    case "TEXT_MESSAGE_CONTENT":
      appendMessageDelta(state, String(event.messageId), String(event.delta ?? ""));
      return {};
    case "TEXT_MESSAGE_END":
      completeMessage(state, String(event.messageId));
      return {};
    case "CUSTOM":
      handleCustomEvent(state, event);
      return {};
    case "TOOL_CALL_START":
      state.toolCalls.push({
        id: String(event.toolCallId),
        name: String(event.toolCallName),
        args: "",
        status: "pending",
      });
      return {};
    case "TOOL_CALL_ARGS":
      updateToolCall(state, String(event.toolCallId), { args: String(event.delta ?? "") });
      return {};
    case "TOOL_CALL_END":
      return { executeToolCallId: String(event.toolCallId) };
    case "TOOL_CALL_RESULT":
      updateToolCall(state, String(event.toolCallId), { status: "completed" });
      return {};
    default:
      return {};
  }
}

export function updateToolCall(state: RuntimeState, toolCallId: string, patch: Partial<ToolCall>): void {
  const toolCall = state.toolCalls.find((item) => item.id === toolCallId);
  if (toolCall) Object.assign(toolCall, patch);
}

function handleCustomEvent(state: RuntimeState, event: AgUiEvent): void {
  if (event.name === "business.progress") {
    const value = event.value as Record<string, unknown>;
    state.progressEvents.push({
      agentId: String(value.agent_id ?? ""),
      runId: String(value.run_id ?? ""),
      taskId: String(value.task_id ?? ""),
      message: String(value.message ?? ""),
      status: value.status === "completed" ? "completed" : "running",
    });
    return;
  }
  if (event.name === "ui.component.render") {
    state.uiRenders.push(event.value as UiRender);
    return;
  }
  if (event.name === "business.error") {
    const value = event.value as Record<string, unknown>;
    const error = value.error as Record<string, unknown> | undefined;
    state.isRunning = false;
    state.error = String(error?.message ?? "Business task failed");
  }
}

function appendMessageDelta(state: RuntimeState, messageId: string, delta: string): void {
  const message = state.messages.find((item) => item.id === messageId);
  if (message) message.content += delta;
}

function completeMessage(state: RuntimeState, messageId: string): void {
  const message = state.messages.find((item) => item.id === messageId);
  if (message) message.complete = true;
}
