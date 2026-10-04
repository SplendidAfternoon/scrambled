/** Tiny WebAudio sound kit: sizzle that follows scrambling, echo pings, serve/fail stingers. All synthesized. */
export class Sfx {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private sizzle: GainNode | null = null;
  private sizzleFilter: BiquadFilterNode | null = null;
  muted = false;

  private ensure(): AudioContext | null {
    if (this.muted) return null;
    if (!this.ctx) {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AC) return null;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.7;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") void this.ctx.resume();
    return this.ctx;
  }

  unlock() {
    this.ensure();
  }

  setMuted(m: boolean) {
    this.muted = m;
    if (this.master) this.master.gain.value = m ? 0 : 0.7;
  }

  startSizzle() {
    const ctx = this.ensure();
    if (!ctx || this.sizzle) return;
    const len = ctx.sampleRate * 2;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) {
      // crackly noise: white noise with random pops
      d[i] = (Math.random() * 2 - 1) * (Math.random() < 0.002 ? 3 : 0.35);
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    this.sizzleFilter = ctx.createBiquadFilter();
    this.sizzleFilter.type = "highpass";
    this.sizzleFilter.frequency.value = 2500;
    this.sizzle = ctx.createGain();
    this.sizzle.gain.value = 0;
    src.connect(this.sizzleFilter).connect(this.sizzle).connect(this.master!);
    src.start();
    (this.sizzle as GainNode & { src?: AudioBufferSourceNode }).src = src;
  }

  /** heat in [0, 1]: how scrambled the pan is right now */
  setHeat(heat: number) {
    if (!this.ctx || !this.sizzle || !this.sizzleFilter) return;
    const t = this.ctx.currentTime;
    this.sizzle.gain.setTargetAtTime(0.03 + 0.25 * heat, t, 0.08);
    this.sizzleFilter.frequency.setTargetAtTime(3800 - 2200 * heat, t, 0.1);
  }

  stopSizzle() {
    const s = this.sizzle as (GainNode & { src?: AudioBufferSourceNode }) | null;
    if (!s || !this.ctx) return;
    s.gain.setTargetAtTime(0, this.ctx.currentTime, 0.05);
    const src = s.src;
    setTimeout(() => src?.stop(), 300);
    this.sizzle = null;
  }

  private tone(freq: number, dur: number, type: OscillatorType, vol: number, when = 0, slideTo?: number) {
    const ctx = this.ensure();
    if (!ctx) return;
    const t0 = ctx.currentTime + when;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t0);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(vol, t0 + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g).connect(this.master!);
    o.start(t0);
    o.stop(t0 + dur + 0.05);
  }

  /** One echo step: a ping whose loudness is the measured echo |F| at the golden eggs. */
  ping(memory: number) {
    this.tone(660 + 440 * memory, 0.12, "sine", 0.05 + 0.18 * memory);
  }

  click() {
    this.tone(1200, 0.04, "square", 0.05);
  }

  win(perfect: boolean) {
    const notes = perfect ? [523, 659, 784, 1047, 1319] : [523, 659, 784];
    notes.forEach((f, i) => this.tone(f, 0.25, "triangle", 0.22, i * 0.08));
  }

  lose() {
    this.tone(220, 0.5, "sawtooth", 0.16, 0, 70);
    this.tone(110, 0.6, "square", 0.08, 0.05, 50);
  }
}
