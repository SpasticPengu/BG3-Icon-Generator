// Glow + colour on the GPU: iconkit.variants.paint (glyph.glow grown from the lines, grammar.tint at the final alpha) as
// WebGL2 passes, so the preview follows every edit (Python takes ~0.4 s at 512). Golden-tested against variants.master
// (iconkit/editor.py golden, app ?golden). Two colours (D26): each stroke set painted alone; every pixel takes the side whose
// lines are nearer (here: the larger blurred line share; Python: the exact nearest line, used for export).
const N = 512;
const EDGE = 12;                            // px: the glow fades out over this band at the image edge (variants.EDGE_FADE)
const VS = `#version 300 es
in vec2 p; void main() { gl_Position = vec4(p, 0., 1.); }`;
const HEAD = `#version 300 es
precision highp float; precision highp int; precision highp sampler2D;
out vec4 o;`;
const PREP = HEAD + `
uniform sampler2D src, pre;
float lq(float g) { float t = clamp(g, 0., 1.) * 200.; int i = min(int(t), 199);
  return mix(texelFetch(pre, ivec2(i, 0), 0).r, texelFetch(pre, ivec2(i + 1, 0), 0).r, t - float(i)); }
void main() { vec4 s = texelFetch(src, ivec2(gl_FragCoord.xy), 0); o = vec4(s.a, lq(s.r) / 100. * s.a, 0., 0.); }`;
// one separable Gaussian pass for both blurs (scipy gaussian_filter: truncate 4, zero outside the image)
const BLUR = HEAD + `
uniform sampler2D src, w; uniform int r1, r2; uniform ivec2 dir; uniform bool first;
void main() { ivec2 p = ivec2(gl_FragCoord.xy); vec4 acc = vec4(0.); int R = max(r1, r2);
  for (int i = -R; i <= R; i++) { ivec2 q = p + dir * i;
    if (q.x < 0 || q.y < 0 || q.x >= ${N} || q.y >= ${N}) continue;
    vec4 v = texelFetch(src, q, 0);
    float a = abs(i) <= r1 ? texelFetch(w, ivec2(i + r1, 0), 0).r : 0.;
    float b = abs(i) <= r2 ? texelFetch(w, ivec2(i + r2, 1), 0).r : 0.;
    acc += first ? vec4(v.xy * a, v.xy * b) : vec4(v.xy * a, v.zw * b); }
  o = acc; }`;
const FINAL = HEAD + `
uniform sampler2D t0, t2, pre; uniform vec4 k; uniform float gam; uniform bool flip; uniform mat3 M;
vec2 lut(int iL, int iA, int iR) { return texelFetch(pre, ivec2((iL * 4 + iA) * 4 + iR, 1), 0).rg; }
void main() { ivec2 p = ivec2(gl_FragCoord.xy); if (flip) p.y = ${N - 1} - p.y;
  vec2 a0 = texelFetch(t0, p, 0).xy; vec4 b = texelFetch(t2, p, 0);
  // the glow fades out at the image edge (variants.edge_window: smoothstep of the distance per axis, multiplied)
  vec2 t = clamp((min(vec2(p), vec2(${N - 1}.) - vec2(p)) + .5) / ${EDGE}., 0., 1.), s = t * t * (3. - 2. * t);
  float w = s.x * s.y, ag0 = pow(clamp(k.z * b.x + k.w * b.z, 0., 1.), gam);
  float al = a0.x, ag = ag0 * w, Eg = min(k.x * b.y + k.y * b.w, ag0) * w, E = a0.y + (1. - al) * Eg, A = al + (1. - al) * ag;
  float L = clamp(100. * E / max(A, 1e-4), texelFetch(pre, ivec2(0, 0), 0).r, texelFetch(pre, ivec2(200, 0), 0).r);
  // trilinear a*b* over lightness (bins of 5), opacity (.1 .35 .7 .95), distance from the centre (.125 ... .875)
  float fL = (clamp(L, 2.5, 97.5) - 2.5) / 5.; int iL = min(int(fL), 18); float tL = fL - float(iL);
  float a = clamp(A, .1, .95); int iA = a < .35 ? 0 : a < .7 ? 1 : 2;
  float tA = iA == 0 ? (a - .1) / .25 : iA == 1 ? (a - .35) / .35 : (a - .7) / .25;
  float fR = (clamp(length(vec2(p) - ${(N - 1) / 2}) / ${N / 2}., .125, .875) - .125) / .25; int iR = min(int(fR), 2); float tR = fR - float(iR);
  vec2 ab = vec2(0.);
  for (int c = 0; c < 8; c++) { int dl = c & 1, da = (c >> 1) & 1, dr = c >> 2;
    ab += lut(iL + dl, iA + da, iR + dr) * (dl == 1 ? tL : 1. - tL) * (da == 1 ? tA : 1. - tA) * (dr == 1 ? tR : 1. - tR); }
  // skimage lab2rgb (D65, 2 degrees), as iconkit/lab.py
  float y = (L + 16.) / 116.; vec3 f = vec3(ab.x / 500. + y, y, max(y - ab.y / 200., 0.));
  vec3 xyz = mix((f - 16. / 116.) / 7.787, f * f * f, step(vec3(.2068966), f)) * vec3(.95047, 1., 1.08883);
  vec3 c = M * xyz;
  vec3 rgb = mix(12.92 * c, 1.055 * pow(max(c, 1e-10), vec3(1. / 2.4)) - .055, step(vec3(.0031308), c));
  o = vec4(clamp(rgb, 0., 1.), A); }`;
const MIX = HEAD + `
uniform sampler2D fA, fB, gA, gB;
void main() { ivec2 p = ivec2(gl_FragCoord.xy); p.y = ${N - 1} - p.y;
  vec4 a = texelFetch(gA, p, 0), b = texelFetch(gB, p, 0);
  o = b.x + .01 * b.z > a.x + .01 * a.z ? texelFetch(fB, p, 0) : texelFetch(fA, p, 0); }`;

const XYZ_FROM_RGB = [[0.412453, 0.357580, 0.180423], [0.212671, 0.715160, 0.072169], [0.019334, 0.119193, 0.950227]];
function inv3(m) {
  const [[a, b, c], [d, e, f], [g, h, i]] = m, A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [[A, -(b * i - c * h), b * f - c * e], [B, a * i - c * g, -(a * f - c * d)], [C, -(a * h - b * g), a * e - b * d]]
    .map(r => r.map(v => v / det));
}
const RGB_FROM_XYZ = inv3(XYZ_FROM_RGB);

export function kernel(sigma) {             // scipy.ndimage gaussian_filter1d weights
  const r = Math.floor(4 * sigma + .5), w = [];
  for (let x = -r; x <= r; x++) w.push(Math.exp(-.5 / (sigma * sigma) * x * x));
  const s = w.reduce((a, b) => a + b, 0);
  return w.map(v => v / s);
}

export class Painter {
  constructor(canvas) {
    canvas.width = canvas.height = N;
    const gl = canvas.getContext("webgl2", {premultipliedAlpha: false, preserveDrawingBuffer: true, antialias: false, alpha: true});
    if (!gl) throw new Error("This browser has no WebGL2");
    if (!gl.getExtension("EXT_color_buffer_float")) throw new Error("WebGL2 without float render targets");
    this.gl = gl;
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    this.prog = {prep: this.program(PREP), blur: this.program(BLUR), final: this.program(FINAL), mix: this.program(MIX)};
    const side = () => ({t0: this.target(), t1: this.target(), t2: this.target(), f: this.target(), src: this.texture()});
    this.sides = [side(), side()];
    this.pres = new Map();
    this.weights = new Map();
    this.ms = 0;
  }
  program(fs) {
    const gl = this.gl, p = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, VS], [gl.FRAGMENT_SHADER, fs]]) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      gl.attachShader(p, s);
    }
    gl.bindAttribLocation(p, 0, "p");
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }
  forget(name) { const t = this.pres.get(name); if (t) { this.gl.deleteTexture(t); this.pres.delete(name); } }   // a custom colour changed
  texture(w = N, h = N, fmt = "RGBA8", data = null) {
    const gl = this.gl, t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    const F = {RGBA8: [gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE], RGBA32F: [gl.RGBA32F, gl.RGBA, gl.FLOAT]}[fmt];
    gl.texImage2D(gl.TEXTURE_2D, 0, F[0], w, h, 0, F[1], F[2], data);
    for (const k of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, k, gl.NEAREST);
    for (const k of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, k, gl.CLAMP_TO_EDGE);
    return t;
  }
  target() {
    const gl = this.gl, tex = this.texture(N, N, "RGBA32F"), fb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return {tex, fb};
  }
  preset(p) {                                // row 0: lq (201 lightness values), row 1: lut (20 x 4 x 4 a*b*)
    if (!this.pres.has(p.name)) {
      const d = new Float32Array(320 * 2 * 4);
      p.lq.forEach((v, i) => d[i * 4] = v);
      p.lut.flat(2).forEach((ab, i) => { d[(320 + i) * 4] = ab[0]; d[(320 + i) * 4 + 1] = ab[1]; });
      this.pres.set(p.name, this.texture(320, 2, "RGBA32F", d));
    }
    return this.pres.get(p.name);
  }
  kernels(th) {                              // glyph.clean: blurs >= .3 (px at 128, x4 at 512), lights / covers >= 0, gamma >= .1
    const key = th.join(",");
    if (!this.weights.has(key)) {
      const [k1, k2] = [kernel(Math.max(th[0], .3) * N / 128), kernel(Math.max(th[1], .3) * N / 128)];
      const w = Math.max(k1.length, k2.length), d = new Float32Array(w * 2 * 4);
      k1.forEach((v, i) => d[i * 4] = v);
      k2.forEach((v, i) => d[(w + i) * 4] = v);
      this.weights.set(key, {tex: this.texture(w, 2, "RGBA32F", d), r1: (k1.length - 1) / 2, r2: (k2.length - 1) / 2});
    }
    return this.weights.get(key);
  }
  pass(name, fb, tex, uni) {
    const gl = this.gl, p = this.prog[name];
    gl.useProgram(p);
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.viewport(0, 0, N, N);
    Object.entries(tex).forEach(([u, t], i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.uniform1i(gl.getUniformLocation(p, u), i);
    });
    for (const [u, [f, ...v]] of Object.entries(uni || {})) gl[f](gl.getUniformLocation(p, u), ...v);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  // rect [x, y, w, h]: only that part of the canvas changed since the last paint (a stroke being drawn): it alone is read
  // and uploaded. A whole-canvas upload from a GPU canvas is a cross-process read back in Firefox (~10 ms a frame).
  paint(s, canvas, p, th, toCanvas, rect = null) {
    const gl = this.gl, pre = this.preset(p), K = this.kernels(th);
    gl.bindTexture(gl.TEXTURE_2D, s.src);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    if (!rect) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, canvas);
    else if (rect[2] > 0 && rect[3] > 0)
      gl.texSubImage2D(gl.TEXTURE_2D, 0, rect[0], rect[1], rect[2], rect[3], gl.RGBA, gl.UNSIGNED_BYTE, canvas.getContext("2d").getImageData(...rect).data);
    this.pass("prep", s.t0.fb, {src: s.src, pre});
    this.pass("blur", s.t1.fb, {src: s.t0.tex, w: K.tex}, {r1: ["uniform1i", K.r1], r2: ["uniform1i", K.r2], dir: ["uniform2i", 1, 0], first: ["uniform1i", 1]});
    this.pass("blur", s.t2.fb, {src: s.t1.tex, w: K.tex}, {r1: ["uniform1i", K.r1], r2: ["uniform1i", K.r2], dir: ["uniform2i", 0, 1], first: ["uniform1i", 0]});
    this.pass("final", toCanvas ? null : s.f.fb, {t0: s.t0.tex, t2: s.t2.tex, pre}, {
      k: ["uniform4f", Math.max(th[2], 0), Math.max(th[3], 0), Math.max(th[4], 0), Math.max(th[5], 0)],
      gam: ["uniform1f", Math.max(th[6], .1)], flip: ["uniform1i", toCanvas ? 1 : 0],
      M: ["uniformMatrix3fv", false, RGB_FROM_XYZ[0].map((_, j) => RGB_FROM_XYZ.map(r => r[j])).flat()]});
  }
  // a = line art canvas (first colour), b = second colour's (or null); p / th = preset + glow recipe per colour; rect: see
  // paint (one colour only). No gl.finish: waiting for the GPU every frame stalled Firefox; ms = time to issue the work.
  render(a, p1, th1, b = null, p2 = null, th2 = null, rect = null) {
    const t = performance.now();
    if (!b) this.paint(this.sides[0], a, p1, th1, true, rect);
    else {
      this.paint(this.sides[0], a, p1, th1, false);
      this.paint(this.sides[1], b, p2, th2, false);
      const [A, B] = this.sides;
      this.pass("mix", null, {fA: A.f.tex, fB: B.f.tex, gA: A.t2.tex, gB: B.t2.tex});
    }
    this.ms = performance.now() - t;
  }
  pixels() {                                 // the master as straight RGBA, rows top first
    const gl = this.gl, px = new Uint8ClampedArray(N * N * 4), out = new Uint8ClampedArray(N * N * 4);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.readPixels(0, 0, N, N, gl.RGBA, gl.UNSIGNED_BYTE, px);
    for (let y = 0; y < N; y++) out.set(px.subarray((N - 1 - y) * N * 4, (N - y) * N * 4), y * N * 4);
    return new ImageData(out, N, N);
  }
}
