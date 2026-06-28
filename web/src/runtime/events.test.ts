import { applyAgUiEvent, createRuntimeState, resetRuntimeState, updateToolCall } from "./events";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function testNormalRunEvents() {
  const state = createRuntimeState();

  applyAgUiEvent(state, { type: "RUN_STARTED", runId: "run_1" });
  applyAgUiEvent(state, {
    type: "CUSTOM",
    name: "business.progress",
    value: { agent_id: "demo_business_agent", message: "working" },
  });
  applyAgUiEvent(state, { type: "TEXT_MESSAGE_START", messageId: "msg_1", role: "assistant" });
  applyAgUiEvent(state, { type: "TEXT_MESSAGE_CONTENT", messageId: "msg_1", delta: "hello" });
  applyAgUiEvent(state, { type: "TEXT_MESSAGE_CONTENT", messageId: "msg_1", delta: " world" });
  applyAgUiEvent(state, { type: "TEXT_MESSAGE_END", messageId: "msg_1" });
  applyAgUiEvent(state, {
    type: "CUSTOM",
    name: "ui.component.render",
    value: {
      component: "demo.result_card",
      component_version: "v1",
      props: {
        title: "Demo",
        summary: "Done",
        items: ["A"],
        attachments: [{ file_id: "file_1", name: "smoke.txt", size_bytes: 16 }],
      },
    },
  });
  applyAgUiEvent(state, { type: "RUN_FINISHED" });

  assertEqual(state.isRunning, false);
  assertEqual(state.runId, "run_1");
  assertDeepEqual(state.progressEvents, [{ agentId: "demo_business_agent", message: "working" }]);
  assertEqual(state.messages[0].content, "hello world");
  assertEqual(state.messages[0].complete, true);
  assertEqual(state.uiRenders[0].component, "demo.result_card");
  assertDeepEqual(
    state.uiRenders[0].props.attachments,
    [{ file_id: "file_1", name: "smoke.txt", size_bytes: 16 }],
  );
}

function testBridgeEventsReturnExecutionEffect() {
  const state = createRuntimeState();

  applyAgUiEvent(state, { type: "TOOL_CALL_START", toolCallId: "tool_1", toolCallName: "get_selected_text" });
  applyAgUiEvent(state, { type: "TOOL_CALL_ARGS", toolCallId: "tool_1", delta: "{\"foo\":true}" });
  const effect = applyAgUiEvent(state, { type: "TOOL_CALL_END", toolCallId: "tool_1" });
  updateToolCall(state, "tool_1", { status: "running" });
  applyAgUiEvent(state, { type: "TOOL_CALL_RESULT", toolCallId: "tool_1" });

  assertDeepEqual(effect, { executeToolCallId: "tool_1" });
  assertEqual(state.toolCalls[0].args, "{\"foo\":true}");
  assertEqual(state.toolCalls[0].status, "completed");
}

function testRunErrorAndReset() {
  const state = createRuntimeState();

  applyAgUiEvent(state, { type: "RUN_STARTED", runId: "run_1" });
  applyAgUiEvent(state, { type: "RUN_ERROR", message: "cancelled" });

  assertEqual(state.isRunning, false);
  assertEqual(state.error, "cancelled");

  resetRuntimeState(state);
  assertDeepEqual(state, createRuntimeState());
}

testNormalRunEvents();
testBridgeEventsReturnExecutionEffect();
testRunErrorAndReset();
console.log("frontend runtime event tests ok");
