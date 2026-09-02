const UINT32_MASK = 0xffffffff;
const UINT64_MASK = (1n << 64n) - 1n;
const UINT64_RANGE = 1n << 64n;
const SPLITMIX_INCREMENT = 0x9e3779b97f4a7c15n;
const SPLITMIX_MIX_1 = 0xbf58476d1ce4e5b9n;
const SPLITMIX_MIX_2 = 0x94d049bb133111ebn;
const D6_REJECTION_LIMIT = UINT64_RANGE - (UINT64_RANGE % 6n);
const HASH_SEPARATOR = "\x1f";

const SHA256_K = Object.freeze([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
  0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
  0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
  0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rightRotate(value, bits) {
  return ((value >>> bits) | (value << (32 - bits))) >>> 0;
}

function sha256Bytes(text) {
  const source = new TextEncoder().encode(String(text));
  const bitLength = source.length * 8;
  const paddedLength = Math.ceil((source.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(source);
  padded[source.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000) >>> 0);
  view.setUint32(paddedLength - 4, bitLength >>> 0);

  let h0 = 0x6a09e667;
  let h1 = 0xbb67ae85;
  let h2 = 0x3c6ef372;
  let h3 = 0xa54ff53a;
  let h4 = 0x510e527f;
  let h5 = 0x9b05688c;
  let h6 = 0x1f83d9ab;
  let h7 = 0x5be0cd19;
  const schedule = new Uint32Array(64);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      schedule[index] = view.getUint32(offset + index * 4);
    }
    for (let index = 16; index < 64; index += 1) {
      const value15 = schedule[index - 15];
      const value2 = schedule[index - 2];
      const sigma0 = rightRotate(value15, 7) ^ rightRotate(value15, 18) ^ (value15 >>> 3);
      const sigma1 = rightRotate(value2, 17) ^ rightRotate(value2, 19) ^ (value2 >>> 10);
      schedule[index] = (schedule[index - 16] + sigma0 + schedule[index - 7] + sigma1) >>> 0;
    }

    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    let f = h5;
    let g = h6;
    let h = h7;

    for (let index = 0; index < 64; index += 1) {
      const sigma1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25);
      const choose = (e & f) ^ (~e & g);
      const temp1 = (h + sigma1 + choose + SHA256_K[index] + schedule[index]) >>> 0;
      const sigma0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (sigma0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
    h5 = (h5 + f) >>> 0;
    h6 = (h6 + g) >>> 0;
    h7 = (h7 + h) >>> 0;
  }

  const digest = new Uint8Array(32);
  const output = new DataView(digest.buffer);
  [h0, h1, h2, h3, h4, h5, h6, h7].forEach((value, index) => {
    output.setUint32(index * 4, value);
  });
  return digest;
}

function toUint64(value, name = "state") {
  let result;
  try {
    if (typeof value === "bigint") result = value;
    else if (typeof value === "number" && Number.isSafeInteger(value)) result = BigInt(value);
    else if (typeof value === "string" && value.trim()) result = BigInt(value);
    else throw new TypeError();
  } catch {
    throw new TypeError(`${name} must be an unsigned 64-bit integer`);
  }
  if (result < 0n || result > UINT64_MASK) {
    throw new RangeError(`${name} must be an unsigned 64-bit integer`);
  }
  return result;
}

export function stableHash64(...parts) {
  const digest = sha256Bytes(parts.map((part) => String(part)).join(HASH_SEPARATOR));
  const view = new DataView(digest.buffer, digest.byteOffset, digest.byteLength);
  return (BigInt(view.getUint32(0)) << 32n) | BigInt(view.getUint32(4));
}

export function splitmix64Next(state) {
  const nextState = (toUint64(state) + SPLITMIX_INCREMENT) & UINT64_MASK;
  let value = nextState;
  value = ((value ^ (value >> 30n)) * SPLITMIX_MIX_1) & UINT64_MASK;
  value = ((value ^ (value >> 27n)) * SPLITMIX_MIX_2) & UINT64_MASK;
  value = (value ^ (value >> 31n)) & UINT64_MASK;
  return { state: nextState, value };
}

export function nextD6FromState(state) {
  let currentState = toUint64(state);
  while (true) {
    const next = splitmix64Next(currentState);
    currentState = next.state;
    if (next.value < D6_REJECTION_LIMIT) {
      return { state: currentState, roll: Number(next.value % 6n) + 1 };
    }
  }
}

export function deriveEmotionRngState(simulationSeed, rootEventCounter = 0) {
  return stableHash64(
    simulationSeed,
    "standing-pair-emotion-d6",
    Number(rootEventCounter),
  );
}

export class DeterministicRng {
  constructor(seed, { state = null } = {}) {
    if (typeof seed !== "string" || seed.length === 0) {
      throw new TypeError("seed must be a non-empty string");
    }
    this.seed = seed;
    this.state = state === null ? stableHash64(seed) : toUint64(state);
  }

  nextUint64() {
    const next = splitmix64Next(this.state);
    this.state = next.state;
    return next.value;
  }

  nextUint32() {
    return Number(this.nextUint64() & BigInt(UINT32_MASK)) >>> 0;
  }

  nextFloat() {
    return this.nextUint32() / 0x100000000;
  }

  choice(items) {
    if (!Array.isArray(items) || items.length === 0) {
      throw new RangeError("choice requires a non-empty array");
    }
    return items[Math.floor(this.nextFloat() * items.length)];
  }

  d6() {
    const next = nextD6FromState(this.state);
    this.state = next.state;
    return next.roll;
  }
}
