import { BrowserRuntimeCore } from "../WEB/runtime_simulation_core.js";

async function readStdin() {
  let text = "";
  for await (const chunk of process.stdin) text += chunk;
  return text;
}

const input = JSON.parse(await readStdin());
const trace = input.trace ?? input;
const bundle = input.bundle ?? trace.bundle;
if (!bundle) throw new TypeError("parity runner input must include bundle");

const core = await BrowserRuntimeCore.create({
  bundle,
  floorId: trace.floor_id,
  seed: trace.seed,
});
const result = {
  schema: "gds.browser_runtime_parity_result.v1",
  version: "1.0.0",
  floor_id: trace.floor_id,
  seed: trace.seed,
  initial_snapshot: core.snapshot(),
  steps: [],
};

for (const step of trace.steps || []) {
  const outcome = core.step(step.elapsed_ms, {
    actorCommands: step.actor_commands || [],
    speechCommands: step.speech_commands || [],
  });
  result.steps.push({
    elapsed_ms: step.elapsed_ms,
    actor_commands: step.actor_commands || [],
    speech_commands: step.speech_commands || [],
    snapshot: outcome.snapshot,
    render_state: outcome.renderState,
    events: outcome.events,
  });
}

core.destroy();
process.stdout.write(JSON.stringify(result));
