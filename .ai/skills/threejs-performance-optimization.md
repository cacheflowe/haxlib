---
name: threejs-performance-optimization
description: Use when profiling or optimizing Three.js WebGL or WebGPU rendering performance and resource lifetime.
---

# Three.js Performance Optimization

> AI assistant skill for writing performant Three.js code (WebGL & WebGPU).
> Adapted from: https://www.utsubo.com/blog/threejs-best-practices-100-tips
> Applies to: Three.js r171+, 2026 browser landscape.

---

## Critical Rules

- **Draw calls < 100/frame.** Triangle count matters far less than draw call count. Check `renderer.info.render.calls`.
- **Dispose everything.** Three.js does NOT garbage-collect GPU resources — geometries, materials, textures, render targets must be manually disposed.
- **Profile before optimizing.** Use `stats-gl`, `renderer.info`, Spector.js, and browser DevTools Performance tab.
- **Never allocate in the render loop.** No `new Vector3()`, `new Matrix4()`, etc. inside `useFrame` / `requestAnimationFrame`.

---

## WebGPU Renderer (r171+)

### Setup

```js
import { WebGPURenderer } from 'three/webgpu';
const renderer = new WebGPURenderer();
await renderer.init(); // REQUIRED — requests GPU adapter/device; fails silently without it
```

- Automatically falls back to WebGL 2 when WebGPU is unavailable — no separate code paths needed.
- `forceWebGL: true` forces WebGL mode for testing fallback behavior.
- Browser support: Chrome/Edge v113+, Firefox v141+ (Win) / v145+ (macOS ARM), Safari v26+.

### When to migrate from WebGL

Migrate when you hit: draw-call bottlenecks, need compute shaders (particles/physics), or complex post-processing chains stutter. If WebGL runs fine, no urgency.

### Performance gains: 2–10× in specific scenarios

- Draw-call-heavy scenes (hundreds of objects)
- Compute-intensive effects (particles, physics)
- Complex shader pipelines

Not universally faster — profile your specific use case.

### Async rendering for compute-heavy scenes

```js
async function animate() {
  await renderer.renderAsync(scene, camera); // ensures compute passes finish first
  requestAnimationFrame(animate);
}
```

Use `renderAsync` only when compute shaders are involved; plain `render()` is fine otherwise.

### Minimize buffer updates

```js
// BAD: many small updates
particles.forEach(p => p.buffer.update());

// GOOD: single batched update
const data = new Float32Array(particles.length * 4);
particles.forEach((p, i) => data.set(p.data, i * 4));
batchBuffer.update(data);
```

### Binding model

WebGPU batches resources into bind groups. Group frequently-updated uniforms (time, camera) together; place static data (textures, materials) separately. Three.js handles this automatically, but understanding it aids debugging.

### Feature detection

```js
const adapter = await navigator.gpu?.requestAdapter();
if (!adapter) return; // fall back to WebGL
const hasTimestamps = adapter.features.has('timestamp-query');
const hasFloat32Filtering = adapter.features.has('float32-filterable');
```

### Debugging

- `chrome://gpu` shows WebGPU status and errors.
- Enable "WebGPU Developer Features" in `chrome://flags`.
- Shader compilation errors are more verbose than WebGL — check console.
- Validation errors include stack traces pointing to the problematic call.

---

## TSL (Three Shader Language)

Node-based material system that compiles to WGSL (WebGPU) or GLSL (WebGL). **Prefer TSL over raw GLSL/WGSL** — write once, run everywhere.

### Basic usage

```js
import { color, positionLocal, sin, time } from 'three/tsl';

const material = new MeshStandardNodeMaterial();
material.colorNode = color(1, 0, 0).mul(sin(time).mul(0.5).add(0.5));
```

### Node material properties

Use `positionNode`, `colorNode`, `normalNode`, `emissiveNode` for programmatic control:

```js
material.positionNode = positionLocal.add(displacement);
material.colorNode = vertexColor;
```

### Reusable functions with `Fn`

```js
import { Fn, float } from 'three/tsl';

const fresnel = Fn(([normal, viewDir, power]) => {
  const dotNV = normal.dot(viewDir).saturate();
  return float(1).sub(dotNV).pow(power);
});
material.emissiveNode = fresnel(normalWorld, viewDirection, 3.0).mul(color);
```

Functions compile once and can be reused across materials.

### Built-in noise (MaterialX)

```js
import { mx_noise_float, mx_fractal_noise_float, mx_noise_vec3 } from 'three/tsl';

const n = mx_noise_float(positionLocal.mul(scale));
const fbm = mx_fractal_noise_float(positionLocal, octaves, lacunarity, gain);
```

No external noise libraries needed.

---

## Compute Shaders (WebGPU)

### GPU particle systems

CPU bottleneck ~50k particles. Compute shaders → millions.

```js
import { instancedArray, compute } from 'three/tsl';

const positions = instancedArray(particleCount, 'vec3'); // persistent GPU buffer
const velocities = instancedArray(particleCount, 'vec3');

const physicsCompute = compute(() => {
  const pos = positions.element(instanceIndex);
  const vel = velocities.element(instanceIndex);
  positions.element(instanceIndex).assign(pos.add(vel.mul(deltaTime)));
});
renderer.compute(physicsCompute);
```

`instancedArray` creates persistent GPU buffers that survive across frames — eliminates CPU→GPU transfer bottleneck.

### Storage textures (read-write)

```js
import { storageTexture, textureStore, uvec2 } from 'three/tsl';
const outputTexture = new StorageTexture(width, height);
const store = textureStore(outputTexture, uvec2(x, y), computedColor);
```

Essential for fluid simulation, image processing, GPU-driven rendering.

### Workgroup shared memory

```js
import { workgroupArray, workgroupBarrier } from 'three/tsl';
const sharedData = workgroupArray('float', 256);
sharedData.element(localIndex).assign(inputData);
workgroupBarrier(); // sync all threads — 10–100× faster than global memory
```

### Indirect draws (GPU-driven rendering)

Let the GPU decide what to render via compute shader output:

```js
const drawIndirectBuffer = new IndirectStorageBufferAttribute(4, 'uint');
const cullCompute = compute(() => {
  if (visible) drawIndirectBuffer.element(1).atomicAdd(1);
});
mesh.drawIndirect = drawIndirectBuffer;
```

Essential for rendering millions of instances with per-frame GPU culling.

---

## Asset Optimization

### Geometry compression

- **Draco**: 90–95% file size reduction. Decompresses in Web Worker (non-blocking).
  ```bash
  gltf-transform draco model.glb compressed.glb --method edgebreaker
  ```
- **Meshopt**: Similar ratios, faster decompression. Test both for your use case.

### Texture compression

- **KTX2 + Basis Universal**: stays compressed on GPU. A 200KB PNG = 20MB+ VRAM; KTX2 reduces ~10×.
- **UASTC**: higher quality, larger files → normal maps, hero textures.
- **ETC1S**: smaller files → environment/secondary textures.

```bash
gltf-transform optimize model.glb output.glb --texture-compress ktx2 --compress draco
```

### Decoder setup (do once)

```js
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';

const dracoLoader = new DRACOLoader();
dracoLoader.setDecoderPath('/draco/');

const ktx2Loader = new KTX2Loader();
ktx2Loader.setTranscoderPath('/basis/');
```

### LOD (Level of Detail)

Swap high-poly → low-poly at distance. 30–40% frame rate improvement in large scenes.

### Texture atlasing

Combine textures into atlases → fewer texture binds → faster rendering, especially on mobile GPUs.

---

## Draw Call Optimization

**Core insight: triangle count matters far less than draw call count.**

### Target: < 100 draw calls per frame

Below 100 = smooth 60fps on most devices. Above 500 = even powerful GPUs struggle.

### InstancedMesh — repeated objects, 1 draw call

```js
const mesh = new InstancedMesh(geometry, material, 1000);
for (let i = 0; i < 1000; i++) {
  matrix.setPosition(positions[i]);
  mesh.setMatrixAt(i, matrix);
}
```

1,000 trees as individual meshes = 1,000 draw calls. InstancedMesh = 1.

### BatchedMesh (r156+) — varied geometries, shared material

Combines different geometries sharing a material into a single draw call.

### Share materials — never create per-mesh

```js
// BAD: new material per mesh
meshes.forEach(m => m.material = new MeshStandardMaterial({ color: 'red' }));

// GOOD: shared reference
const shared = new MeshStandardMaterial({ color: 'red' });
meshes.forEach(m => m.material = shared);
```

### Merge static geometry

```js
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
const merged = mergeGeometries([geo1, geo2, geo3]);
const mesh = new Mesh(merged, sharedMaterial);
```

### Frustum culling

Enabled by default (`mesh.frustumCulled = true`). Disable only for always-visible objects (skyboxes). Ensure bounding boxes are accurate for it to work correctly.

---

## Memory Management

### Dispose pattern

```js
function cleanupMesh(mesh) {
  mesh.geometry.dispose();
  if (Array.isArray(mesh.material)) {
    mesh.material.forEach(disposeMaterial);
  } else {
    disposeMaterial(mesh.material);
  }
  scene.remove(mesh);
}

function disposeMaterial(mat) {
  Object.values(mat).forEach(prop => {
    if (prop?.isTexture) prop.dispose();
  });
  mat.dispose();
}
```

A single 4K texture = 64MB+ VRAM. Monitor `renderer.info.memory` — if counts grow, you have leaks.

### GLTF ImageBitmap textures require explicit close

```js
texture.source.data.close?.(); // ImageBitmap requires this
texture.dispose();
```

### Object pooling

Pre-allocate and reuse frequently created/destroyed objects to avoid allocation spikes and GC pauses:

```js
class ObjectPool {
  constructor(factory, reset, initialSize = 20) {
    this.pool = Array.from({ length: initialSize }, () => {
      const obj = factory(); obj.visible = false; return obj;
    });
    this.factory = factory;
    this.reset = reset;
  }
  acquire() { const obj = this.pool.pop() || this.factory(); obj.visible = true; return obj; }
  release(obj) { this.reset(obj); obj.visible = false; this.pool.push(obj); }
}
```

Pre-warm pools during loading.

### Texture caching

```js
const textureCache = new Map();
function getTexture(url) {
  if (!textureCache.has(url)) textureCache.set(url, textureLoader.load(url));
  return textureCache.get(url);
}
```

### Render targets

Always `renderTarget.dispose()` when done — each allocates framebuffer memory.

---

## Shader & Material Optimization

### Mobile: use `mediump` precision

`mediump` runs ~2× faster than `highp` on mobile GPUs. Only use `highp` for depth/positions.

### Minimize varyings (< 3 for mobile)

Pack data into `vec4`s instead of many individual varyings.

### Branchless GPU code

```glsl
// BAD: branching kills GPU parallelism
if (value > 0.5) color = colorA; else color = colorB;

// GOOD: branchless
color = mix(colorB, colorA, step(0.5, value));
```

### Pack data into RGBA channels

Store 4 values per texel → 75% fewer texture fetches.

### Avoid dynamic loops

Fixed-bound or unrolled loops allow compiler optimization; dynamic bounds prevent it.

### Shader program reuse

Three.js reuses programs for identical shaders. Unnecessary material/uniform variations cause program proliferation — avoid creating needless variations.

---

## Lighting & Shadows

### Rules of thumb

- **≤ 3 active lights.** Beyond that, bake or use environment maps.
- **PointLight shadows cost 6× draw calls** (one per cube face). 2 PointLights × 10 objects = 120 extra draw calls.
- **Bake lightmaps** for static scenes — free at render time (use Blender bake or `@react-three/lightmap`).
- **Fake shadows** (semi-transparent plane + radial gradient) are often good enough.

### Shadow map sizes

| Target | Size |
|--------|------|
| Mobile | 512–1024 |
| Desktop | 1024–2048 |
| Quality-critical | 4096 |

Larger = quadratically more memory.

### Static shadow optimization

```js
renderer.shadowMap.autoUpdate = false;       // stop rendering shadows every frame
renderer.shadowMap.needsUpdate = true;       // trigger manually only when needed
```

### Tighten shadow camera frustum

Always fit to your scene — don't use defaults:

```js
directionalLight.shadow.camera.left = -10;
directionalLight.shadow.camera.right = 10;
directionalLight.shadow.camera.top = 10;
directionalLight.shadow.camera.bottom = -10;
```

### Environment maps for ambient light

```js
const envMap = pmremGenerator.fromScene(scene).texture;
scene.environment = envMap;
```

### Cascaded Shadow Maps for large scenes

```js
import { CSM } from 'three/addons/csm/CSM.js';
const csm = new CSM({ maxFar: camera.far, cascades: 4, shadowMapSize: 2048 });
```

Desktop: 4 cascades. Mobile: 2.

---

## Post-Processing

### WebGL: use pmndrs/postprocessing

Auto-merges effects into fewer shader passes:

```js
import { EffectComposer, Bloom, Vignette } from 'postprocessing';
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new EffectPass(camera, new Bloom(), new Vignette()));
```

### WebGPU: use native TSL post-processing

```js
import { pass, bloom, fxaa } from 'three/tsl';
const postProcessing = new PostProcessing(renderer);
const scenePass = pass(scene, camera);
postProcessing.outputNode = scenePass.pipe(bloom()).pipe(fxaa());
```

### Configuration checklist

- Disable native `antialias` when post-processing handles AA (SMAA/FXAA).
- Set `powerPreference: 'high-performance'`.
- Disable renderer tone mapping (`NoToneMapping`); add `ToneMappingEffect` as last effect.
- Add antialiasing as the **final** pass.
- Merge compatible effects into a single `EffectPass`.
- Consider half-resolution rendering + upscale to double frame rate.

### Bloom parameters

| Param | Typical Range |
|-------|--------------|
| intensity | 0.5–2.0 |
| luminanceThreshold | 0.8–1.0 |
| radius | 0.5–1.0 |

Use selective bloom (`luminanceThreshold`) — not everything should glow.

---

## Loading & Web Vitals

- **Lazy load** 3D below the fold via `IntersectionObserver`.
- **Code-split** Three.js with dynamic `import()`.
- **Preload** critical above-the-fold assets: `<link rel="preload" href="/model.glb" as="fetch" crossorigin>`.
- **Progressive loading**: show low-res model immediately, swap in high-res async.
- **Placeholder geometry**: wireframe box during load.
- **Web Workers** for physics, procedural generation, heavy processing.
- **Chunk streaming** for large environments — load/unload sections by camera proximity.

---

## React Three Fiber (R3F) Specifics

### Core performance rules

```jsx
// BAD: triggers React re-render every frame
const [rotation, setRotation] = useState(0);
useFrame(() => setRotation(r => r + 0.01));

// GOOD: direct Three.js mutation via ref
const meshRef = useRef();
useFrame((_, delta) => { meshRef.current.rotation.x += delta * speed; });
```

- **Never `setState` in `useFrame`** — mutate refs directly.
- **Never allocate in `useFrame`** — memoize with `useMemo`.
- **Use `delta`** for frame-rate independence.
- **`frameloop="demand"`** for static scenes; call `invalidate()` on changes.
- **`visible={false}`** instead of conditional rendering — avoids buffer/shader recompilation.
- **`React.memo`** for expensive components.
- **`useGLTF.preload('/model.glb')`** to front-load assets.
- **`<Suspense fallback={<Loader />}>`** for loading states.

### Cleanup on unmount

```jsx
useEffect(() => {
  return () => { geometry.dispose(); material.dispose(); texture.dispose(); };
}, []);
```

---

## Debugging & Profiling Tools

| Tool | Purpose |
|------|---------|
| `stats-gl` | Real-time FPS/CPU/GPU metrics (WebGL + WebGPU) |
| `lil-gui` | Live parameter tweaking panels |
| `Spector.js` | WebGL frame capture — see every draw call, bind, shader |
| `three-mesh-bvh` | Fast raycasting for 80k+ polygon meshes |
| `r3f-perf` | Drop-in R3F performance monitor |
| `renderer.info` | Draw calls, triangles, geometry/texture counts |
| Chrome DevTools Performance | Frame timing, GC pauses, blocking JS |

### Monitor renderer stats

```js
console.log('Calls:', renderer.info.render.calls);
console.log('Triangles:', renderer.info.render.triangles);
console.log('Geometries:', renderer.info.memory.geometries);
console.log('Textures:', renderer.info.memory.textures);
```

Numbers should stay stable — if they climb, you have a leak.

### Context loss recovery

```js
renderer.domElement.addEventListener('webglcontextlost', (e) => { e.preventDefault(); });
renderer.domElement.addEventListener('webglcontextrestored', () => { /* reinitialize */ });
```

### Animation loop

Prefer `renderer.setAnimationLoop(callback)` over manual `requestAnimationFrame`. Handles XR sessions automatically. Stop with `renderer.setAnimationLoop(null)`.

---

## Quick Reference: Anti-Patterns

| Anti-Pattern | Fix |
|---|---|
| `new Vector3()` in render loop | Pre-allocate, reuse via `useMemo` or module scope |
| New material per mesh | Share a single material instance |
| Not disposing resources | Always `.dispose()` geometry, material, texture, render target |
| `setState` in `useFrame` | Mutate ref directly |
| Conditional mount/unmount for toggling | Use `visible` prop |
| Many small GPU buffer updates | Batch into single typed array update |
| PointLight shadows on many objects | Bake, fake, or use DirectionalLight |
| Unbounded draw calls | Instance, batch, merge, cull |
| Full-resolution post-processing | Consider half-res + upscale |
| Dynamic shader loop bounds | Use fixed or unrolled loops |
