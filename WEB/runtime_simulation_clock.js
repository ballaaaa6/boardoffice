function requireInteger(value, label, { minimum = 0 } = {}) {
  if (!Number.isInteger(value) || value < minimum) {
    throw new TypeError(`${label} must be an integer >= ${minimum}`);
  }
  return value;
}

export class FixedStepClock {
  constructor({ stepMs = 60, maxCatchupMs = 1000 } = {}) {
    this.stepMs = requireInteger(stepMs, "stepMs", { minimum: 1 });
    this.maxCatchupMs = requireInteger(maxCatchupMs, "maxCatchupMs", {
      minimum: this.stepMs,
    });
    this.accumulatorMs = 0;
    this.simulationClockMs = 0;
  }

  pushElapsed(elapsedMs) {
    requireInteger(elapsedMs, "elapsedMs");
    const cappedElapsedMs = Math.min(elapsedMs, this.maxCatchupMs);
    this.accumulatorMs = Math.min(
      this.accumulatorMs + cappedElapsedMs,
      this.maxCatchupMs,
    );
    const slices = [];
    const maximumSlices = Math.floor(this.maxCatchupMs / this.stepMs);
    while (this.accumulatorMs >= this.stepMs && slices.length < maximumSlices) {
      this.accumulatorMs -= this.stepMs;
      this.simulationClockMs += this.stepMs;
      slices.push(this.stepMs);
    }
    return slices;
  }

  reset({ simulationClockMs = 0 } = {}) {
    this.accumulatorMs = 0;
    this.simulationClockMs = requireInteger(simulationClockMs, "simulationClockMs");
  }
}
