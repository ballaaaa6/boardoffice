const DEFAULT_INTERVAL_MS = 100;
const DEFAULT_TIMEOUT_MS = 5000;
const RETRY_BASE_MS = 250;
const RETRY_MAX_MS = 4000;

function numberOr(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

export class RuntimeRenderClient {
  constructor({
    renderer,
    apiRoot = "",
    intervalMs = 100,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    fetchImpl = globalThis.fetch?.bind(globalThis),
    requestAnimationFrameImpl = globalThis.requestAnimationFrame?.bind(globalThis),
    cancelAnimationFrameImpl = globalThis.cancelAnimationFrame?.bind(globalThis),
    now = () => globalThis.performance?.now?.() ?? Date.now(),
    requestBody = () => ({ elapsed_ms: 60, autopilot: true, compact: true }),
    onState = () => {},
    onError = () => {},
  } = {}) {
    if (!renderer || typeof renderer.render !== "function") {
      throw new TypeError("RuntimeRenderClient requires a renderer");
    }
    if (typeof fetchImpl !== "function") throw new TypeError("RuntimeRenderClient requires fetch");
    if (typeof requestAnimationFrameImpl !== "function") {
      throw new TypeError("RuntimeRenderClient requires requestAnimationFrame");
    }
    this.renderer = renderer;
    this.apiRoot = String(apiRoot).replace(/\/$/, "");
    this.intervalMs = Math.max(16, numberOr(intervalMs, DEFAULT_INTERVAL_MS));
    this.timeoutMs = Math.max(100, numberOr(timeoutMs, DEFAULT_TIMEOUT_MS));
    this.fetchImpl = fetchImpl;
    this.requestAnimationFrameImpl = requestAnimationFrameImpl;
    this.cancelAnimationFrameImpl = cancelAnimationFrameImpl || globalThis.cancelAnimationFrame?.bind(globalThis);
    this.now = now;
    this.requestBody = requestBody;
    this.onState = onState;
    this.onError = onError;
    this.running = false;
    this.busy = false;
    this.retryAttempt = 0;
    this.generation = 0;
    this.rafHandle = null;
    this.pollHandle = null;
    this.abortController = null;
  }

  _reportError(error) {
    try {
      this.onError(error);
    } catch (_) {
      // A telemetry callback must not stop the render client.
    }
  }

  _scheduleFrame(generation) {
    if (!this.running || generation !== this.generation) return;
    this.rafHandle = this.requestAnimationFrameImpl((timestamp) => {
      if (!this.running || generation !== this.generation) return;
      try {
        this.renderer.render(timestamp ?? this.now());
      } catch (error) {
        this._reportError(error);
      }
      this._scheduleFrame(generation);
    });
  }

  _schedulePoll(delayMs, generation) {
    if (!this.running || generation !== this.generation) return;
    this.pollHandle = globalThis.setTimeout(async () => {
      if (!this.running || generation !== this.generation) return;
      if (this.busy) {
        this._schedulePoll(this.intervalMs, generation);
        return;
      }
      this.busy = true;
      try {
        await this.tickOnce();
        this.retryAttempt = 0;
        this._schedulePoll(this.intervalMs, generation);
      } catch (error) {
        this.retryAttempt = Math.min(this.retryAttempt + 1, 6);
        const retryDelay = Math.min(RETRY_BASE_MS * (2 ** (this.retryAttempt - 1)), RETRY_MAX_MS);
        this._reportError(error);
        this._schedulePoll(retryDelay, generation);
      } finally {
        this.busy = false;
      }
    }, Math.max(0, delayMs));
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.generation += 1;
    const generation = this.generation;
    const manifestPromise = this.renderer.loadManifest?.();
    if (manifestPromise?.catch) manifestPromise.catch((error) => this._reportError(error));
    this._scheduleFrame(generation);
    this._schedulePoll(0, generation);
  }

  stop() {
    if (!this.running && this.rafHandle === null && this.pollHandle === null) return;
    this.running = false;
    this.generation += 1;
    if (this.pollHandle !== null) globalThis.clearTimeout(this.pollHandle);
    if (this.rafHandle !== null && this.cancelAnimationFrameImpl) {
      this.cancelAnimationFrameImpl(this.rafHandle);
    }
    this.pollHandle = null;
    this.rafHandle = null;
    this.abortController?.abort();
    this.abortController = null;
    this.busy = false;
  }

  async tickOnce(extra = {}) {
    const controller = new AbortController();
    this.abortController = controller;
    const timeout = globalThis.setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const requested = {
        ...this.requestBody(),
        ...extra,
        renderer: "canvas",
      };
      const response = await this.fetchImpl(`${this.apiRoot}/api/tick`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requested),
        signal: controller.signal,
      });
      let payload;
      try {
        payload = await response.json();
      } catch (_) {
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.ok) throw new Error(payload?.error || response.statusText || `HTTP ${response.status}`);
      if (payload?.renderer !== "canvas" || !payload.render_state) {
        throw new Error("canvas tick returned no render state");
      }
      this.renderer.setState(payload.render_state);
      this.onState(payload);
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") throw new Error(`request timeout after ${this.timeoutMs}ms`);
      throw error;
    } finally {
      globalThis.clearTimeout(timeout);
      if (this.abortController === controller) this.abortController = null;
    }
  }
}
