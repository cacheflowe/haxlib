---
name: threejs-react-three-fiber-gpu-particles
description: Use when building GPU particle systems, shaders, or buffer geometries with React Three Fiber and Three.js.
---

The magical world of Particles with React Three Fiber and Shaders
=================================================================

from: https://blog.maximeheckel.com/posts/the-magical-world-of-particles-with-react-three-fiber-and-shaders/

Nov 8, 2022Nov 8, 2022

Since writing [The Study of Shaders with React Three Fiber](https://blog.maximeheckel.com/posts/the-study-of-shaders-with-react-three-fiber/), I've continued building new scenes to perfect my shader skills and learn new techniques to achieve even more ambitious creations. While shaders on their own unlocked a new realm of what's possible to do on the web, there's one type of 3D object that I've overlooked until recently: **particles**!

Whether it's to create galaxies, stars, smoke, fire, or even some other abstract effects, particles are the best tool to help you create scenes that can feel _truly magical_ 🪄.

However, particles can also feel quite intimidating at first. It takes a lot of practice to get familiar with the core concepts of particle-based scenes such as **attributes** or **buffer geometries** and advanced ones like **combining them with custom shaders** or using **Frame Buffer Objects** to push those scenes even further.

In this article, you will find all the _tips and techniques_ I learned regarding particles, from creating simple particle systems with **standard and buffer geometries** to customizing how they look, controlling their movement with **shaders**, and techniques to scale the number of particles even further. You'll also get a deeper understanding of **attributes**, a key shader concept I overlooked in my previous blog post that is essential for these use cases.

👉 This article assumes you have basic knowledge about shaders and GLSL, or read [The Study of Shaders with React Three Fiber](https://blog.maximeheckel.com/posts/the-study-of-shaders-with-react-three-fiber/).

The GLSL code in the demos will be displayed as _strings_ as it was easier to make that work with React Three Fiber on Sandpack.

To learn more on how to import .glsl files in your React project, check out [glslify-loader](https://github.com/glslify/glslify-loader).

An introduction to attributes
-----------------------------

Before we can jump into creating gorgeous particle-based scenes with React Three Fiber, we have to talk about **attributes**.

### What are attributes?

**Attributes are pieces of data associated with each vertex of a mesh**. If you've been playing with React Three Fiber and created some meshes, you've already used attributes without knowing! Each geometry associated with a mesh has a set of pre-defined attributes such as:

*   The _position attribute_: an array of data representing all the positions of each vertex of a given geometry.
    
*   The _uv attribute_: an array of data representing the UV coordinates of a given geometry.
    

These are just two examples among many possibilities, but you'll find these in pretty much any geometry you'll use. You can easily take a peek at them to see what kind of data it contains:

Logging the attributes of a geometry

```
const Scene = () => {
  const mesh = useRef();

  useEffect(() => {
    console.log(mesh.current.geometry.attributes);
  }, []);

  return <mesh ref={mesh}>{/* ... */}</mesh>;
};
```

You should see something like this:

Screenshot showcasing the output printed when logging the attributes of a geometry

If you're feeling confused right now, do not worry 😄. I was too! Seeing data like this can feel intimidating at first, but we'll make sense of all this just below.

### Playing with attributes

This long array with _lots_ of numbers represents **the value of the x, y, and z coordinates for each vertex of our geometry**. It's one-dimensional (no nested data), where each value x, y, and z of a given vertex is right next to the ones from the other vertex. I built the little widget below to illustrate in a more approachable way how the values of that position array translate to points in space:

Position attributes array to vertex visualizer2.73.13.34.16.99.40.62.23.36.18.53.78.06.72.08.15.13.34.20.26.12.41.30.12.73.13.34.16.99.40.62.23.36.18.53.78.06.72.08.15.13.34.20.26.12.41.30.1

As you can see, to read this array, we need to read values _3 by 3_ simply because our vertices have three values. To read the UV attribute array, however, we need to read the values _2 by 2_, as UV coordinates only have two values, x and y.

We will see later in this article how to define attributes and how we can tell our renderer how to "read" the data to build _custom geometries_.

Now that we know how to interpret that data, we can start having some fun with it. You can easily manipulate and modify attributes and create some nice effects without the need to touch shader code.

Below is an example where we use attributes to twist a boxGeometry along its y-axis.

```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Color, Vector3, Quaternion } from "three";
import './scene.css';

const TwistedBox = () => {
  // This reference gives us direct access to the mesh
  const mesh = useRef();
  const quaternion = new Quaternion();

  useEffect(() => {
    // Get the current attributes of the geometry
    const currentPositions = mesh.current.geometry.attributes.position;
    // Copy the attributes
    const originalPositions = currentPositions.clone();
    const originalPositionsArray = originalPositions?.array || [];

    // Go through each vector (series of 3 values) and modify the values
    for (let i = 0; i < originalPositionsArray.length; i=i+3) {
      const modifiedPositionVector = new Vector3(originalPositionsArray[i], originalPositionsArray[i+1], originalPositionsArray[i+2]);
      const upVector = new Vector3(0, 1, 0);

      // Rotate along the y axis (0, 1, 0)
      quaternion.setFromAxisAngle(
        upVector, 
        (Math.PI / 180) * (modifiedPositionVector.y + 10) * 100 // the higher along the y axis the vertex is, the more we rotate
      );
      modifiedPositionVector.applyQuaternion(quaternion);

      // Apply the modified position vector coordinates to the current position attributes array
      currentPositions.array[i] = modifiedPositionVector.x 
      currentPositions.array[i+1] = modifiedPositionVector.y
      currentPositions.array[i+2] = modifiedPositionVector.z
    }
    // Set the needsUpdate flag to "true"
    currentPositions.needsUpdate = true;
  }, [])

  return (
    <mesh ref={mesh} position={[0, 0, 0]}>
      <boxGeometry args={[1, 1, 1, 10, 10, 10]} />
      <meshLambertMaterial color="hotpink" emissive="hotpink" />
    </mesh>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [1.5, 1.5, 1.5] }}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[-1, 2, 2]} intensity={4} />
      <TwistedBox />
      <OrbitControls autoRotate />
    </Canvas>
  );
};


export default Scene;
```


We do this effect by:

*   Copying the original position attribute of the geometry.
    

```
// Get the current attributes of the geometry
const currentPositions = mesh.current.geometry.attributes.position;
// Copy the attributes
const originalPositions = currentPositions.clone();
```

*   Looping through each value of the array and applying a rotation.
    

  ```javascript
  const originalPositionsArray = originalPositions?.array || [];  // Go through each vector (series of 3 values) and modify the values
  for (let i = 0; i < originalPositionsArray.length; i = i + 3) {
    // ...
  }
  ```

*   Pass the newly generated data to the geometry to replace the original position attribute array.
    

```javascript
// Apply the modified position vector coordinates to the current position attributes array
currentPositions.array[i] = modifiedPositionVector.x;
currentPositions.array[i + 1] = modifiedPositionVector.y;
currentPositions.array[i + 2] = modifiedPositionVector.z;
```

### Attributes with Shaders

I briefly touched upon this subject when I introduced the notion of _uniforms_ in [The Study of Shaders with React Three Fiber](https://blog.maximeheckel.com/posts/the-study-of-shaders-with-react-three-fiber/) but could not find a meaningful way to tackle it without making an already long article even longer.

We saw that **we use uniforms to pass data from our Javascript code to a shader**. Attributes are pretty similar in that regard as well, but there is one key difference:

*   Data passed to a shader via a uniform remains constant between each vertex of a mesh (and pixels as well)
    
*   Data passed via an attribute can be _different_ for each vertex, allowing us to more fine-tuned controls of our vertex shader.
    

You can only pass attributes to the vertex shader! If you want to use them in a fragment shader, you will need to pass the data using a _varying_.

Diagram illustrating how to pass the attributes from a geometry from the vertex shader to the fragment shader using varyings.

You can see that attributes allow us **to control each vertex of a mesh**, but not only! For particle-based scenes, we will heavily rely on them to:

*   position our particles in space
    
*   move, scale, or animate our particles through time
    
*   customize each particle in a unique way
    

That is why it's necessary to have a somewhat clear understanding of attributes before getting started with particles.

Particles in React Three Fiber
------------------------------

Now that we know more about attributes, we can finally bring our focus to the core of this article: **particles**.

### Our first scene with Particles

Remember how we can define a **mesh** as follows: **mesh = geometry + material**? Well, that definition also applies to **points**, the construct we use to create particles:

**points = geometry + material**

The only difference at this stage is that our points will use a specific type of material, the **pointsMaterial**.

You can read more about those constructs by heading to the corresponding section in the Three.js documentation:

*   [pointsMaterial](https://threejs.org/docs/#api/en/materials/PointsMaterial)
    
*   [points](https://threejs.org/docs/?q=points#api/en/objects/Points)
    

That is also where you'll find all the options documented, as I may skip detailing some of those in this article.

Below you'll find an example of a particle system in React Three Fiber. As you can see, we're creating a system in the shape of a sphere by using

*   points
    
*   sphereGeometry for our geometry
    
*   pointsMaterial for our material
    

```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import './scene.css';

const BasicParticles = () => {
  // This reference gives us direct access to our points
  const points = useRef();

  // You can see that, like our mesh, points also takes a geometry and a material,
  // but a specific material => pointsMaterial
  return (
    <points ref={points}>
      <sphereGeometry args={[1, 48, 48]} />
      <pointsMaterial color="#5786F5" size={0.015} sizeAttenuation />
    </points>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [1.5, 1.5, 1.5] }}>
      <ambientLight intensity={0.5} />
      <BasicParticles />
      <OrbitControls autoRotate />
    </Canvas>
  );
};


export default Scene;

```

With pointsMaterial you can:

1.  make your particles bigger or smaller using the size prop.
    
2.  make distant particles look smaller than closer particles using the sizeAttenuation prop.
    

Now you may ask me: _this is great, but what if I want to position my particles more organically? What about creating a randomized cloud of particles?_ Well, this is where the notion of attributes comes into play!

### Using BufferGeometry and attributes to create custom geometries

In Three.js and React Three Fiber, we can create _custom geometries_ thanks to the use of:

*   bufferGeometry
    
*   bufferAttribute
    
*   our newly acquired knowledge of attributes 🎉
    

When working with Particles, using a bufferGeometry can be really powerful: it gives us full-control over the placement of each particle, and later we'll also see how this lets us animate them.

Let's take a look at how we can define a custom geometry in React Three Fiber with the following code example:

Custom geometry with bufferGeometry and bufferAttribute

```
const CustomGeometryParticles = () => {
  const particlesPosition = [
    /* ... */
  ];

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.015}
        color="#5786F5"
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
};
```

In the code snippet above, we can see that:

1.  We are rendering a bufferGeometry as the geometry of our points.
    
2.  In this bufferGeometry, we're using the bufferAttribute element that lets us set the position attribute of our geometry.
    

Now let's take a look at the props that we're passing to the bufferAttribute element:

*   count is the **total number of vertex our geometry** will have. In our case, it is the number of particles we will end up rendering.
    
*   attach is how we specify the **name of our attribute**. In this case, we set it as attributes-position so the data we're feeding to the bufferAttribute is available under the position attribute.
    
*   itemSize represents the **number of values from our attributes array associated with one item/vertex**. In this case, it's set to 3 as we're dealing with the position attribute that has three components x, y, and z.
    

I'd recommend reading [the documentation on the attribute notation](https://docs.pmnd.rs/react-three-fiber/api/objects#piercing-into-nested-properties).

I did not do it and lost a couple hours due to a silly mistake the first time I tried custom geometries 🤦‍♂️

[Maxime@MaximeHeckel](https://twitter.com/MaximeHeckel)

well... that's 2 hours of my life I won't get back https://t.co/go8qCC5cVG

[0](https://twitter.com/intent/like?tweet_id=1564632534356357120)[3:14 PM - Aug 30, 2022](https://twitter.com/MaximeHeckel/status/1564632534356357120)

Now when it comes to creating the attributes array itself, let's look at the particlePositions array located in our particle scene code.

Generating a position attribute array

```
const count = 2000;

const particlesPosition = useMemo(() => {
  // Create a Float32Array of count*3 length
  // -> we are going to generate the x, y, and z values for 2000 particles
  // -> thus we need 6000 items in this array
  const positions = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    // Generate random values for x, y, and z on every loop
    let x = (Math.random() - 0.5) * 2;
    let y = (Math.random() - 0.5) * 2;
    let z = (Math.random() - 0.5) * 2;

    // We add the 3 values to the attribute array for every loop
    positions.set([x, y, z], i * 3);
  }

  return positions;
}, [count]);
```

1.  First, we specify a Float32Array with a length of count \* 3. We're going to render count particles, e.g. 2000, and each particle has three values (x, y, and z) associated with its position, i.e. **\*6000 values in total**.
    
2.  Then, we create a loop, and **for each particle, we set all the values for x, y, and z**. In this case, we're using some level of randomness to position our particles randomly.
    
3.  Finally, we're adding all three values to the array at the position i \* 3 with positions.set(\[x,y,z\], i\*3).
    

The code sandbox below showcases what we can render with this technique of using custom geometries. In this example, I created two different position attribute arrays that place particles randomly:

*   at the surface of a sphere
    
*   in a box, which you can render by changing the shape prop to box and hitting reload.
    
```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

const CustomGeometryParticles = (props) => {
  const { count, shape } = props;

  // This reference gives us direct access to our points
  const points = useRef();

  // Generate our positions attributes array
  const particlesPosition = useMemo(() => {
    const positions = new Float32Array(count * 3);

    if (shape === "box") {
      for (let i = 0; i < count; i++) {
        let x = (Math.random() - 0.5) * 2;
        let y = (Math.random() - 0.5) * 2;
        let z = (Math.random() - 0.5) * 2;

        positions.set([x, y, z], i * 3);
      }
    }

    if (shape === "sphere") {
      const distance = 1;
     
      for (let i = 0; i < count; i++) {
        const theta = THREE.MathUtils.randFloatSpread(360); 
        const phi = THREE.MathUtils.randFloatSpread(360); 

        let x = distance * Math.sin(theta) * Math.cos(phi)
        let y = distance * Math.sin(theta) * Math.sin(phi);
        let z = distance * Math.cos(theta);

        positions.set([x, y, z], i * 3);
      }
    }

    return positions;
  }, [count, shape]);

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial size={0.015} color="#5786F5" sizeAttenuation depthWrite={false} />
    </points>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [1.5, 1.5, 1.5] }}>
      <ambientLight intensity={0.5} />
      {/* Try to change the shape prop to "box" and hit reload! */}
      <CustomGeometryParticles count={2000} shape="sphere"/>
      <OrbitControls autoRotate />
    </Canvas>
  );
};


export default Scene;

```

We can see that using custom geometries lets us get a more organic render for our particle system, which looks prettier and opens up way more possibilities than standard geometries ✨.

Customizing and animating Particles with Shaders
------------------------------------------------

Now that we know how to create a particle system based on custom geometries, we can start focusing on the fun part: animating particles! 🎉

There are two ways to approach animating particles:

1.  Using attributes (easier)
    
2.  Using shaders (a bit harder)
    

We'll look at both ways, although, as you may expect, if you know me a little bit through the work I share on [Twitter](https://twitter.com/MaximeHeckel), we're going to focus a lot on the second one. A little bit of challenge never hurts!

### Animating Particles with attributes

For this part, we will see how to animate our particles by _updating_ our position attribute array _on every frame_ using the useFrame hook. If you've animated meshes with React Three Fiber before, this method should be straightforward!

We just saw how to create an attributes array; updating it is pretty much the same process:

*   We loop through the current values of the attributes array. It can be all the values or just some of them.
    
*   Update them.
    
*   And finally, the most important: set the needsUpdate field of our position attribute to true.
    

If you forget the last step, your scene will remain static!

Animate particles via attributes in React Three Fiber

```
useFrame((state) => {
  const { clock } = state;

  for (let i = 0; i < count; i++) {
    const i3 = i * 3;

    points.current.geometry.attributes.position.array[i3] +=
      Math.sin(clock.elapsedTime + Math.random() * 10) * 0.01;
    points.current.geometry.attributes.position.array[i3 + 1] +=
      Math.cos(clock.elapsedTime + Math.random() * 10) * 0.01;
    points.current.geometry.attributes.position.array[i3 + 2] +=
      Math.sin(clock.elapsedTime + Math.random() * 10) * 0.01;
  }

  points.current.geometry.attributes.position.needsUpdate = true;
});
```

The scene rendered below uses this technique to move the particles around their initial position, making the particle system feel a bit more _alive_ ✨

```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

const CustomGeometryParticles = (props) => {
  const { count } = props;

  // This reference gives us direct access to our points
  const points = useRef();

  // Generate our positions attributes array
  const particlesPosition = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const distance = 1;
    
    for (let i = 0; i < count; i++) {
      const theta = THREE.MathUtils.randFloatSpread(360); 
      const phi = THREE.MathUtils.randFloatSpread(360); 

      let x = distance * Math.sin(theta) * Math.cos(phi)
      let y = distance * Math.sin(theta) * Math.sin(phi);
      let z = distance * Math.cos(theta);

      positions.set([x, y, z], i * 3);
    }
    

    return positions;
  }, [count]);

  useFrame((state) => {
    const { clock } = state;
    
    for (let i = 0; i < count; i++) {
      const i3 = i * 3;


      points.current.geometry.attributes.position.array[i3] += Math.sin(clock.elapsedTime + Math.random() * 10) * 0.01;
      points.current.geometry.attributes.position.array[i3 + 1] += Math.cos(clock.elapsedTime + Math.random() * 10) * 0.01;
      points.current.geometry.attributes.position.array[i3 + 2] += Math.sin(clock.elapsedTime + Math.random() * 10) * 0.01;
    }

    points.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial size={0.012} color="#5786F5" sizeAttenuation depthWrite={false} />
    </points>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [1.5, 1.5, 1.5] }}>
      <ambientLight intensity={0.5} />
      <CustomGeometryParticles count={2000} />
      <OrbitControls />
    </Canvas>
  );
};


export default Scene;

```

Despite being the easiest, **this method is also pretty expensive**: on _every frame_, we have to loop through very long attribute arrays and update them. _Over and over_. As you might expect, this becomes a real problem as the number of particles grows. Thus it's preferable to delegate that part to the GPU with a sweet shader, which also has the added benefit to be more elegant. (a totally non-biased opinion from someone who dedicated weeks of their life working with shaders 😄).

### How to animate our particles with a vertex shader

First and foremost, it's time to say goodbye to our pointsMaterial 👋, and replace it with a shaderMaterial as follows:

How to use a custom shaderMaterial with particles and a custom buffer geometry

```
const CustomGeometryParticles = (props) => {
  const { count } = props;
  const points = useRef();

  const particlesPosition = useMemo(() => ({
    // We set out positions here as we did before
  )}, [])

  const uniforms = useMemo(() => ({
    uTime: {
      value: 0.0
    },
    // Add any other attributes here
  }), [])

  useFrame((state) => {
    const { clock } = state;

    points.current.material.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <shaderMaterial
        depthWrite={false}
        fragmentShader={fragmentShader}
        vertexShader={vertexShader}
        uniforms={uniforms}
      />
    </points>
  );
}
```

As we learned in [The Study of Shaders with React Three Fiber](https://blog.maximeheckel.com/posts/the-study-of-shaders-with-react-three-fiber/), we need to specify two functions for our shaderMaterial:

*   the fragment shader: this is where we'll focus on the next part to customize our particles
    
*   the vertex shader: this is where we'll animate our particles
    

For this example, we're going to make our particles rotate. Some good folks worked on some GLSL packages to abstract these functions away for us like [dmnsgn/glsl-rotate](https://github.com/dmnsgn/glsl-rotate).

You can load these functions on your projects using glsify-loader. The code sandbox below will have the code of this project copied over for simplicity.

Vertex shader code that applies a rotation along the y-axis

```
uniform float uTime;

void main() {
  vec3 particlePosition = position * rotation3dY(uTime * 0.2);

  vec4 modelPosition = modelMatrix * vec4(particlePosition, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;
  gl_PointSize = 3.0;
}
```

As you can see in the snippet above, when it comes to the code, **animating particles using a shader is very similar to animating a mesh**. With the vertex shader, you get to interact with the vertices of a geometry, **which are the particles themselves in this use case**.

Since we're there, let's iterate on that shader code to make the resulting scene even better: make the particles close to the center of the sphere move faster than the ones on the outskirts.

Enhanced version of the previous vertex shader

```
uniform float uTime;
uniform float uRadius;

void main() {
  float distanceFactor = pow(uRadius - distance(position, vec3(0.0)), 2.0);
  vec3 particlePosition = position * rotation3dY(uTime * 0.2 * distanceFactor);

  vec4 modelPosition = modelMatrix * vec4(particlePosition, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;
  gl_PointSize = 3.0;
}
```

Which renders as the following once we wire this shader to our React Three Fiber code with a uTime and uRadius uniform:

App.js:

```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

import vertexShader from "!!raw-loader!./vertexShader.glsl";
import fragmentShader from "!!raw-loader!./fragmentShader.glsl";

const CustomGeometryParticles = (props) => {
  const { count } = props;
  const radius = 2;

  // This reference gives us direct access to our points
  const points = useRef();

  // Generate our positions attributes array
  const particlesPosition = useMemo(() => {
    const positions = new Float32Array(count * 3);
    
    for (let i = 0; i < count; i++) {
      const distance = Math.sqrt(Math.random()) * radius;
      const theta = THREE.MathUtils.randFloatSpread(360); 
      const phi = THREE.MathUtils.randFloatSpread(360); 

      let x = distance * Math.sin(theta) * Math.cos(phi)
      let y = distance * Math.sin(theta) * Math.sin(phi);
      let z = distance * Math.cos(theta);

      positions.set([x, y, z], i * 3);
    }
    
    return positions;
  }, [count]);

  const uniforms = useMemo(() => ({
    uTime: {
      value: 0.0
    },
    uRadius: {
      value: radius
    }
  }), [])

  useFrame((state) => {
    const { clock } = state;

    points.current.material.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <shaderMaterial
        depthWrite={false}
        fragmentShader={fragmentShader}
        vertexShader={vertexShader}
        uniforms={uniforms}
      />
    </points>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [2.0, 2.0, 2.0] }}>
      <ambientLight intensity={0.5} />
      <CustomGeometryParticles count={4000} />
      <OrbitControls />
    </Canvas>
  );
};


export default Scene;
```

vertexShader.glsl:

```
uniform float uTime;
uniform float uRadius;

// Source: https://github.com/dmnsgn/glsl-rotate/blob/main/rotation-3d-y.glsl.js
mat3 rotation3dY(float angle) {
  float s = sin(angle);
  float c = cos(angle);
  return mat3(
    c, 0.0, -s,
    0.0, 1.0, 0.0,
    s, 0.0, c
  );
}


void main() {
  float distanceFactor = pow(uRadius - distance(position, vec3(0.0)), 1.5);
  vec3 particlePosition = position * rotation3dY(uTime * 0.3 * distanceFactor);

  vec4 modelPosition = modelMatrix * vec4(particlePosition, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;
  gl_PointSize = 3.0;
}

```

fragementShader.glsl:

```

void main() {
  gl_FragColor = vec4(0.34, 0.53, 0.96, 1.0);
}
```

### How to change the size and appearance of our particles with shaders

This entire time, our particles were _simple tiny squares_, which is a bit boring. In this part, we'll look at how to fix this with some well-thought-out shader code.

First, let's look at the size. All our particles are the _same size_ right now which does not really give off an _organic_ vibe to this scene. To address that, we can tweak the gl\_PointSize property in our vertex shader code.

We can do multiple things with the point size:

*   Making it a function of the position with some Perlin noise
    
*   Making it a function of the distance from the center of your geometry
    
*   Simply making it random
    

Anything is possible! For this example, we'll pick the second one:


App.js:

```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

import vertexShader from "!!raw-loader!./vertexShader.glsl";
import fragmentShader from "!!raw-loader!./fragmentShader.glsl";

const CustomGeometryParticles = (props) => {
  const { count } = props;
  const radius = 2;

  // This reference gives us direct access to our points
  const points = useRef();

  // Generate our positions attributes array
  const particlesPosition = useMemo(() => {
    const positions = new Float32Array(count * 3);
    
    for (let i = 0; i < count; i++) {
      const distance = Math.sqrt(Math.random()) * radius;
      const theta = THREE.MathUtils.randFloatSpread(360); 
      const phi = THREE.MathUtils.randFloatSpread(360); 

      let x = distance * Math.sin(theta) * Math.cos(phi)
      let y = distance * Math.sin(theta) * Math.sin(phi);
      let z = distance * Math.cos(theta);

      positions.set([x, y, z], i * 3);
    }
    
    return positions;
  }, [count]);

  const uniforms = useMemo(() => ({
    uTime: {
      value: 0.0
    },
    uRadius: {
      value: radius
    }
  }), [])

  useFrame((state) => {
    const { clock } = state;

    points.current.material.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <shaderMaterial
        depthWrite={false}
        fragmentShader={fragmentShader}
        vertexShader={vertexShader}
        uniforms={uniforms}
      />
    </points>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [2.0, 2.0, 2.0] }}>
      <ambientLight intensity={0.5} />
      <CustomGeometryParticles count={4000} />
      <OrbitControls />
    </Canvas>
  );
};


export default Scene;

```

vertexShader.glsl:

```
uniform float uTime;
uniform float uRadius;

// Source: https://github.com/dmnsgn/glsl-rotate/blob/main/rotation-3d-y.glsl.js
mat3 rotation3dY(float angle) {
  float s = sin(angle);
  float c = cos(angle);
  return mat3(
    c, 0.0, -s,
    0.0, 1.0, 0.0,
    s, 0.0, c
  );
}


void main() {
  float distanceFactor = pow(uRadius - distance(position, vec3(0.0)), 1.5);
  float size = distanceFactor * 1.5 + 3.0;
  vec3 particlePosition = position * rotation3dY(uTime * 0.3 * distanceFactor);

  vec4 modelPosition = modelMatrix * vec4(particlePosition, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;

  gl_PointSize = size;
  // Size attenuation;
  gl_PointSize *= (1.0 / - viewPosition.z);
}

```

fragementShader.glsl:

```
void main() {
  gl_FragColor = vec4(0.34, 0.53, 0.96, 1.0);
}
```

When we replaced our pointsMaterial with a shaderMaterial we lost the \`sizeAttenuation\* prop.

If you want to easily reproduce it in a vertex shader, the code to add is:

`gl_PointSize = size * (1.0 / - viewPosition.z);`

Now, when it comes to the **particle pattern** itself, we can modify it in the **fragment shader**. I like to make my particles look like _tiny points of light_ that we can luckily achieve with a few lines of code.

```
varying float vDistance;

void main() {
  vec3 color = vec3(0.34, 0.53, 0.96);
  // Create a strength variable that's bigger the closer to the center of the particle the pixel is
  float strength = distance(gl_PointCoord, vec2(0.5));
  strength = 1.0 - strength;
  // Make it decrease in strength *faster* the further from the center by using a power of 3
  strength = pow(strength, 3.0);

  // Ensure the color is only visible close to the center of the particle
  color = mix(vec3(0.0), color, strength);
  gl_FragColor = vec4(color, strength);
}
```

Fragment shader that changes the appearance of our particles

```
varying float vDistance;

void main() {
  vec3 color = vec3(0.34, 0.53, 0.96);
  // Create a strength variable that's bigger the closer to the center of the particle the pixel is
  float strength = distance(gl_PointCoord, vec2(0.5));
  strength = 1.0 - strength;
  // Make it decrease in strength *faster* the further from the center by using a power of 3
  strength = pow(strength, 3.0);

  // Ensure the color is only visible close to the center of the particle
  color = mix(vec3(0.0), color, strength);
  gl_FragColor = vec4(color, strength);
}
```

We can now make the colors of the particles a parameter of the material through a uniform and also make it a function of the distance to the center, for example:

Enhanced version of the previous fragment shader

```
varying float vDistance;

void main() {
  vec3 color = vec3(0.34, 0.53, 0.96);
  float strength = distance(gl_PointCoord, vec2(0.5));
  strength = 1.0 - strength;
  strength = pow(strength, 3.0);

  // Make particle close to the *center of the scene* a warmer color
  // and the ones on the outskirts a cooler color
  color = mix(color, vec3(0.97, 0.70, 0.45), vDistance * 0.5);
  color = mix(vec3(0.0), color, strength);
  // Here we're passing the strength in the alpha channel to make sure the outskirts
  // of the particle are not visible
  gl_FragColor = vec4(color, strength);
}
```

In the end, **we get a beautiful set of custom particles with just a few lines of GLSL** sprinkled on top of our particle system 🪄

App.js:

```
import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

import vertexShader from "!!raw-loader!./vertexShader.glsl";
import fragmentShader from "!!raw-loader!./fragmentShader.glsl";

const CustomGeometryParticles = (props) => {
  const { count } = props;
  const radius = 2;

  // This reference gives us direct access to our points
  const points = useRef();

  // Generate our positions attributes array
  const particlesPosition = useMemo(() => {
    const positions = new Float32Array(count * 3);
    
    for (let i = 0; i < count; i++) {
      const distance = Math.sqrt(Math.random()) * radius;
      const theta = THREE.MathUtils.randFloatSpread(360); 
      const phi = THREE.MathUtils.randFloatSpread(360); 

      let x = distance * Math.sin(theta) * Math.cos(phi)
      let y = distance * Math.sin(theta) * Math.sin(phi);
      let z = distance * Math.cos(theta);

      positions.set([x, y, z], i * 3);
    }
    
    return positions;
  }, [count]);

  const uniforms = useMemo(() => ({
    uTime: {
      value: 0.0
    },
    uRadius: {
      value: radius
    }
  }), [])

  useFrame((state) => {
    const { clock } = state;

    points.current.material.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particlesPosition.length / 3}
          array={particlesPosition}
          itemSize={3}
        />
      </bufferGeometry>
      <shaderMaterial
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        fragmentShader={fragmentShader}
        vertexShader={vertexShader}
        uniforms={uniforms}
      />
    </points>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [2.0, 2.0, 2.0] }}>
      <ambientLight intensity={0.5} />
      <CustomGeometryParticles count={4000} />
      <OrbitControls />
    </Canvas>
  );
};

export default Scene;
```

vertexShader.glsl:

```
uniform float uTime;
uniform float uRadius;

varying float vDistance;

// Source: https://github.com/dmnsgn/glsl-rotate/blob/main/rotation-3d-y.glsl.js
mat3 rotation3dY(float angle) {
  float s = sin(angle);
  float c = cos(angle);
  return mat3(
    c, 0.0, -s,
    0.0, 1.0, 0.0,
    s, 0.0, c
  );
}


void main() {
  float distanceFactor = pow(uRadius - distance(position, vec3(0.0)), 1.5);
  float size = distanceFactor * 10.0 + 10.0;
  vec3 particlePosition = position * rotation3dY(uTime * 0.3 * distanceFactor);

  vDistance = distanceFactor;

  vec4 modelPosition = modelMatrix * vec4(particlePosition, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;

  gl_PointSize = size;
  // Size attenuation;
  gl_PointSize *= (1.0 / - viewPosition.z);
}
```

fragmentShader.glsl:

```
varying float vDistance;

void main() {
  vec3 color = vec3(0.34, 0.53, 0.96);
  float strength = distance(gl_PointCoord, vec2(0.5));
  strength = 1.0 - strength;
  strength = pow(strength, 3.0);

  color = mix(color, vec3(0.97, 0.70, 0.45), vDistance * 0.5);
  color = mix(vec3(0.0), color, strength);
  gl_FragColor = vec4(color, strength);
}
```

For a better effect, set the blending prop of the shaderMaterial to THREE.AdditiveBlending. This allows particles that are superposed to add their color to one another and create a beautiful staturated look.

Going beyond with Frame Buffer Objects
--------------------------------------

What if we wanted to render _a lot more particles_ onto our scene? What about **100's of thousands**? That would be pretty cool, right? With this _advanced technique_ I'm about to show you, it is possible! And on top of that, with little to no frame drop 🔥!

This technique is named **Frame Buffer Object** ([FBO](https://en.wikipedia.org/wiki/Framebuffer_object)). I stumbled upon it when I wanted to reproduce one of [@winkerVSbecks](https://twitter.com/winkerVSbecks) [attractor](https://en.wikipedia.org/wiki/Attractor) scenes from his blog post [Three ways to create 3D particle effects](https://varun.ca/three-js-particles/).

Long story short, I wanted to build the same attractor effect but with _shaders_. The problem was that in an attractor, the position of a particle is dictated by its previous one, which doesn't work by just relying on the position attributes and a vertex shader: there's no way to get the updated position back to our Javascript code after it's been updated in our vertex shader and feed it back to the shader to calculate the next one! Thankfully, thanks to using an FBO, I figured out a way to render [this scene](https://r3f.maximeheckel.com/attractor).

It was mainly thanks to [this Stackoverflow answer](https://stackoverflow.com/a/43119909/2059960) that I figured out the solution and learned the existence of FBO.

### How does a Frame Buffer Object work with particles?

I've seen many people using this technique in Three.js codebases. Here is how it goes: instead of initiating our particles positions array and passing it as an attribute and then render them, we are going to have 3 phases with two render passes.

1.  The **simulation pass**. We set the positions of the particles as a **Data Texture** to a shader material. They are then read, returned, and sometimes modified in the material's _fragment shader_ (you heard me right!).
    
2.  Create a WebGLRenderTarget, a "texture" we can render to _off-screen_ where we will add a small scene containing our material from the simulation pass and a small plane. We then set it as the _current render target_, thus rendering our simulation material with its Data Texture that is filled with position data.
    
3.  The **render pass**. We can now read the texture rendered in the render target. **The texture data is the positions array of our particles**, which we can now pass as a uniform to our particles' shaderMaterial.
    

It may sound counter-intuitive for a fragment shader to store/return position data when, so far, we mainly used it for colors. If you think about it, the meaning of the data doesn't really matter, it's more about _its shape_:

*   Colors in a fragment shader are a vec4 for the R, G, B, and A color components.
    
*   In this case, we're also passing a vec4 for x, y, and z and a constant value 1.0 for the last component that we do not need.
    

In the end, we're using the simulation pass as a **buffer** to store data **and do a lot of heavy calculations** on the GPU by processing our positions in a fragment shader, and we do that on _every_ _single_ _frame_. Hence the name Frame Buffer Object. I hope I did not lose you there 😅. Maybe the diagram below, as well as the following code snippet will help 👇:

Diagram illustrating how the Frame Buffer Objects allows to store and update particles position data in a vertex shader and then be read as a texture.

Setting up a simulation material

```
import { extend } from '@react-three/fiber';

// ... other imports

const generatePositions = (width, height) => {
  // we need to create a vec4 since we're passing the positions to the fragment shader
  // data textures need to have 4 components, R, G, B, and A
  const length = width * height * 4;
  const data = new Float32Array(length);

  // Fill Float32Array here

  return data;
};

// Create a custom simulation shader material
class SimulationMaterial extends THREE.ShaderMaterial {
  constructor(size) {
    // Create a Data Texture with our positions data
    const positionsTexture = new THREE.DataTexture(
      generatePositions(size, size),
      size,
      size,
      THREE.RGBAFormat,
      THREE.FloatType
    );
    positionsTexture.needsUpdate = true;

    const simulationUniforms = {
      // Pass the positions Data Texture as a uniform
      positions: { value: positionsTexture },
    };

    super({
      uniforms: simulationUniforms,
      vertexShader: simulationVertexShader,
      fragmentShader: simulationFragmentShader,
    });
  }
}

// Make the simulation material available as a JSX element in our canva
extend({ SimulationMaterial: SimulationMaterial });
```

```
import { useFBO } from '@react-three/drei';
import { useFrame, createPortal } from '@react-three/fiber';

const FBOParticles = () => {
  const size = 128;

  // This reference gives us direct access to our points
  const points = useRef();
  const simulationMaterialRef = useRef();

  // Create a camera and a scene for our FBO
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(
    -1,
    1,
    1,
    -1,
    1 / Math.pow(2, 53),
    1
  );

  // Create a simple square geometry with custom uv and positions attributes
  const positions = new Float32Array([
    -1, -1, 0, 1, -1, 0, 1, 1, 0, -1, -1, 0, 1, 1, 0, -1, 1, 0,
  ]);

  const uvs = new Float32Array([0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1]);

  // Create our FBO render target
  const renderTarget = useFBO(size, size, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    stencilBuffer: false,
    type: THREE.FloatType,
  });

  // Generate a "buffer" of vertex of size "size" with normalized coordinates
  const particlesPosition = useMemo(() => {
    const length = size * size;
    const particles = new Float32Array(length * 3);
    for (let i = 0; i < length; i++) {
      let i3 = i * 3;
      particles[i3 + 0] = (i % size) / size;
      particles[i3 + 1] = i / size / size;
    }
    return particles;
  }, [size]);

  const uniforms = useMemo(
    () => ({
      uPositions: {
        value: null,
      },
    }),
    []
  );

  useFrame((state) => {
    const { gl, clock } = state;

    // Set the current render target to our FBO
    gl.setRenderTarget(renderTarget);
    gl.clear();
    // Render the simulation material with square geometry in the render target
    gl.render(scene, camera);
    // Revert to the default render target
    gl.setRenderTarget(null);

    // Read the position data from the texture field of the render target
    // and send that data to the final shaderMaterial via the `uPositions` uniform
    points.current.material.uniforms.uPositions.value = renderTarget.texture;

    simulationMaterialRef.current.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <>
      {/* Render off-screen our simulation material and square geometry */}
      {createPortal(
        <mesh>
          <simulationMaterial ref={simulationMaterialRef} args={[size]} />
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={positions.length / 3}
              array={positions}
              itemSize={3}
            />
            <bufferAttribute
              attach="attributes-uv"
              count={uvs.length / 2}
              array={uvs}
              itemSize={2}
            />
          </bufferGeometry>
        </mesh>,
        scene
      )}
      <points ref={points}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={particlesPosition.length / 3}
            array={particlesPosition}
            itemSize={3}
          />
        </bufferGeometry>
        <shaderMaterial
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          fragmentShader={fragmentShader}
          vertexShader={vertexShader}
          uniforms={uniforms}
        />
      </points>
    </>
  );
};
```

Here I'm relying on two tools provided by the pmndrs team:

*   the useFBO hook from [@react-three/drei](https://github.com/pmndrs/drei#usefbo) to set up my render target.
    
*   the createPortal from [@react-three/fiber](https://github.com/pmndrs/react-three-fiber) to render the necessary objects used by my render target _off-screen_
    

If you want to learn more about Three.js render targets, you should check out [this introduction article](https://r105.threejsfundamentals.org/threejs/lessons/threejs-rendertargets.html)

### Creating magical scenes with FBO

To demonstrate the power of FBO, let's look at two scenes I built with this technique 👀.

The first one renders a particle system in the shape of a sphere with randomly positioned points. In the simulationMaterial, I applied a _curl-noise_ to the position data of the particles, which yields the gorgeous effect you can see below ✨!

App.js:

```
import { OrbitControls, useFBO } from "@react-three/drei";
import { Canvas, useFrame, extend, createPortal } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

import SimulationMaterial from './SimulationMaterial';

import vertexShader from "!!raw-loader!./vertexShader.glsl";
import fragmentShader from "!!raw-loader!./fragmentShader.glsl";

extend({ SimulationMaterial: SimulationMaterial });

const FBOParticles = () => {
  const size = 128;

  const points = useRef();
  const simulationMaterialRef = useRef();

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1 / Math.pow(2, 53), 1);
  const positions = new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, -1, 0, 1, 1, 0, -1, 1, 0]);
  const uvs = new Float32Array([
    0, 0,  // bottom-left
    1, 0,  // bottom-right
    1, 1,  // top-right
    0, 0,  // bottom-left
    1, 1,  // top-right
    0, 1   // top-left
  ]);

  const renderTarget = useFBO(size, size, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    stencilBuffer: false,
    type: THREE.FloatType,
  });

  const particlesPosition = useMemo(() => {
    const length = size * size;
    const particles = new Float32Array(length * 3);
    for (let i = 0; i < length; i++) {
      let i3 = i * 3;
      particles[i3 + 0] = (i % size) / size;
      particles[i3 + 1] = i / size / size;
    }
    return particles;
  }, [size]);

  const uniforms = useMemo(() => ({
    uPositions: {
      value: null,
    }
  }), [])

  useFrame((state) => {
    const { gl, clock } = state;

    gl.setRenderTarget(renderTarget);
    gl.clear();
    gl.render(scene, camera);
    gl.setRenderTarget(null);

    points.current.material.uniforms.uPositions.value = renderTarget.texture;

    simulationMaterialRef.current.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <>
      {createPortal(
        <mesh>
          <simulationMaterial ref={simulationMaterialRef} args={[size]} />
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={positions.length / 3}
              array={positions}
              itemSize={3}
            />
            <bufferAttribute
              attach="attributes-uv"
              count={uvs.length / 2}
              array={uvs}
              itemSize={2}
            />
          </bufferGeometry>
        </mesh>,
        scene
      )}
      <points ref={points}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={particlesPosition.length / 3}
            array={particlesPosition}
            itemSize={3}
          />
        </bufferGeometry>
        <shaderMaterial
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          fragmentShader={fragmentShader}
          vertexShader={vertexShader}
          uniforms={uniforms}
        />
      </points>
    </>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [1.5, 1.5, 2.5] }}>
      <ambientLight intensity={0.5} />
      <FBOParticles />
      <OrbitControls />
    </Canvas>
  );
};

export default Scene;
```

SimulationMaterial.js:

```
import simulationVertexShader from '!!raw-loader!./simulationVertexShader.glsl';
import simulationFragmentShader from '!!raw-loader!./simulationFragmentShader.glsl';
import * as THREE from "three";

const getRandomData = (width, height) => {
  // we need to create a vec4 since we're passing the positions to the fragment shader
  // data textures need to have 4 components, R, G, B, and A
  const length = width * height * 4 
  const data = new Float32Array(length);
    
  for (let i = 0; i < length; i++) {
    const stride = i * 4;

    const distance = Math.sqrt(Math.random()) * 2.0;
    const theta = THREE.MathUtils.randFloatSpread(360); 
    const phi = THREE.MathUtils.randFloatSpread(360); 

    data[stride] =  distance * Math.sin(theta) * Math.cos(phi)
    data[stride + 1] =  distance * Math.sin(theta) * Math.sin(phi);
    data[stride + 2] =  distance * Math.cos(theta);
    data[stride + 3] =  1.0; // this value will not have any impact
  }
  
  return data;
}

class SimulationMaterial extends THREE.ShaderMaterial {
  constructor(size) {
    const positionsTexture = new THREE.DataTexture(
      getRandomData(size, size),
      size,
      size,
      THREE.RGBAFormat,
      THREE.FloatType
    );
    positionsTexture.needsUpdate = true;

    const simulationUniforms = {
      positions: { value: positionsTexture },
      uFrequency: { value: 0.25 },
      uTime: { value: 0 },
    };

    super({
      uniforms: simulationUniforms,
      vertexShader: simulationVertexShader,
      fragmentShader: simulationFragmentShader,
    });
  }
}

export default SimulationMaterial;
```

simulationVertexShader.js:

```

varying vec2 vUv;

void main() {
  vUv = uv;

  vec4 modelPosition = modelMatrix * vec4(position, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;
}
```

simulationFragmentShader.js:

```
uniform sampler2D positions;
uniform float uTime;
uniform float uFrequency;

varying vec2 vUv;


// Source: https://github.com/drcmda/glsl-curl-noise2
// and: https://github.com/guoweish/glsl-noise-simplex/blob/master/3d.glsl

//
// Description : Array and textureless GLSL 2D/3D/4D simplex
//               noise functions.
//      Author : Ian McEwan, Ashima Arts.
//  Maintainer : ijm
//     Lastmod : 20110822 (ijm)
//     License : Copyright (C) 2011 Ashima Arts. All rights reserved.
//               Distributed under the MIT License. See LICENSE file.
//               https://github.com/ashima/webgl-noise
//

vec3 mod289(vec3 x) {
  return x - floor(x * (1.0 / 289.0)) * 289.0;
}

vec4 mod289(vec4 x) {
  return x - floor(x * (1.0 / 289.0)) * 289.0;
}

vec4 permute(vec4 x) {
     return mod289(((x*34.0)+1.0)*x);
}

vec4 taylorInvSqrt(vec4 r)
{
  return 1.79284291400159 - 0.85373472095314 * r;
}

float snoise(vec3 v)
  {
  const vec2  C = vec2(1.0/6.0, 1.0/3.0) ;
  const vec4  D = vec4(0.0, 0.5, 1.0, 2.0);

// First corner
  vec3 i  = floor(v + dot(v, C.yyy) );
  vec3 x0 =   v - i + dot(i, C.xxx) ;

// Other corners
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min( g.xyz, l.zxy );
  vec3 i2 = max( g.xyz, l.zxy );

  //   x0 = x0 - 0.0 + 0.0 * C.xxx;
  //   x1 = x0 - i1  + 1.0 * C.xxx;
  //   x2 = x0 - i2  + 2.0 * C.xxx;
  //   x3 = x0 - 1.0 + 3.0 * C.xxx;
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy; // 2.0*C.x = 1/3 = C.y
  vec3 x3 = x0 - D.yyy;      // -1.0+3.0*C.x = -0.5 = -D.y

// Permutations
  i = mod289(i);
  vec4 p = permute( permute( permute(
             i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
           + i.y + vec4(0.0, i1.y, i2.y, 1.0 ))
           + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));

// Gradients: 7x7 points over a square, mapped onto an octahedron.
// The ring size 17*17 = 289 is close to a multiple of 49 (49*6 = 294)
  float n_ = 0.142857142857; // 1.0/7.0
  vec3  ns = n_ * D.wyz - D.xzx;

  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);  //  mod(p,7*7)

  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_ );    // mod(j,N)

  vec4 x = x_ *ns.x + ns.yyyy;
  vec4 y = y_ *ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);

  vec4 b0 = vec4( x.xy, y.xy );
  vec4 b1 = vec4( x.zw, y.zw );

  //vec4 s0 = vec4(lessThan(b0,0.0))*2.0 - 1.0;
  //vec4 s1 = vec4(lessThan(b1,0.0))*2.0 - 1.0;
  vec4 s0 = floor(b0)*2.0 + 1.0;
  vec4 s1 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));

  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
  vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;

  vec3 p0 = vec3(a0.xy,h.x);
  vec3 p1 = vec3(a0.zw,h.y);
  vec3 p2 = vec3(a1.xy,h.z);
  vec3 p3 = vec3(a1.zw,h.w);

//Normalise gradients
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
  p0 *= norm.x;
  p1 *= norm.y;
  p2 *= norm.z;
  p3 *= norm.w;

// Mix final noise value
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1),
                                dot(p2,x2), dot(p3,x3) ) );
  }


vec3 snoiseVec3( vec3 x ){

  float s  = snoise(vec3( x ));
  float s1 = snoise(vec3( x.y - 19.1 , x.z + 33.4 , x.x + 47.2 ));
  float s2 = snoise(vec3( x.z + 74.2 , x.x - 124.5 , x.y + 99.4 ));
  vec3 c = vec3( s , s1 , s2 );
  return c;

}


vec3 curlNoise( vec3 p ){
  
  const float e = .1;
  vec3 dx = vec3( e   , 0.0 , 0.0 );
  vec3 dy = vec3( 0.0 , e   , 0.0 );
  vec3 dz = vec3( 0.0 , 0.0 , e   );

  vec3 p_x0 = snoiseVec3( p - dx );
  vec3 p_x1 = snoiseVec3( p + dx );
  vec3 p_y0 = snoiseVec3( p - dy );
  vec3 p_y1 = snoiseVec3( p + dy );
  vec3 p_z0 = snoiseVec3( p - dz );
  vec3 p_z1 = snoiseVec3( p + dz );

  float x = p_y1.z - p_y0.z - p_z1.y + p_z0.y;
  float y = p_z1.x - p_z0.x - p_x1.z + p_x0.z;
  float z = p_x1.y - p_x0.y - p_y1.x + p_y0.x;

  const float divisor = 1.0 / ( 2.0 * e );
  return normalize( vec3( x , y , z ) * divisor );

}


void main() {
  vec3 pos = texture2D(positions, vUv).rgb;
  vec3 curlPos = texture2D(positions, vUv).rgb;

  pos = curlNoise(pos * uFrequency + uTime * 0.1);
  curlPos = curlNoise(curlPos * uFrequency + uTime * 0.1);
  curlPos += curlNoise(curlPos * uFrequency * 2.0) * 0.5;

  gl_FragColor = vec4(mix(pos, curlPos, sin(uTime)), 1.0);
}
```

vertexShader.js:

```
uniform sampler2D uPositions;
uniform float uTime;

void main() {
  vec3 pos = texture2D(uPositions, position.xy).xyz;

  vec4 modelPosition = modelMatrix * vec4(pos, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;

  gl_PointSize = 3.0;
  // Size attenuation;
  gl_PointSize *= step(1.0 - (1.0/64.0), position.x) + 0.5;
}
```

fragmentShader.js:

```
void main() {
  vec3 color = vec3(0.34, 0.53, 0.96);
  gl_FragColor = vec4(color, 1.0);
}
```

In this scene, we:

*   render 128 x 128 (the resolution of our render target) particles.
    
*   apply a curl noise to each of our particles in our simulation pass.
    
*   pass all that data along to the renderMaterial that takes care to render each vertex with that position data and also the particle size using the gl\_pointSize property.
    

I kept the number of particles "low" on purpose, so I could be sure it performs well on most computers, but I'd invite you to fork this scene and increase the resolution of the render target for an even more impressive effect!

On my laptop, a 2020 M1 Macbook Pro, I can push this demo way over 1 million particles 🤯.

Finally, one last scene, just for fun! I ported to React Three Fiber a Three.js demo from [an article](http://barradeau.com/blog/?p=621) written by [@nicoptere](https://twitter.com/nicoptere) that does a pretty good job at deep diving into the FBO technique.

App.js:

```
import { OrbitControls, useFBO } from "@react-three/drei";
import { Canvas, useFrame, extend, createPortal } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import './scene.css';

import SimulationMaterial from './SimulationMaterial';

import vertexShader from "!!raw-loader!./vertexShader.glsl";
import fragmentShader from "!!raw-loader!./fragmentShader.glsl";

extend({ SimulationMaterial: SimulationMaterial });

const FBOParticles = () => {
  const size = 128;

  // This reference gives us direct access to our points
  const points = useRef();
  const simulationMaterialRef = useRef();

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1 / Math.pow(2, 53), 1);
  const positions = new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, -1, 0, 1, 1, 0, -1, 1, 0]);
   const uvs = new Float32Array([
    0, 0,  // bottom-left
    1, 0,  // bottom-right
    1, 1,  // top-right
    0, 0,  // bottom-left
    1, 1,  // top-right
    0, 1   // top-left
  ]);

  const renderTarget = useFBO(size, size, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    stencilBuffer: false,
    type: THREE.FloatType,
  });

  // Generate our positions attributes array
  const particlesPosition = useMemo(() => {
    const length = size * size;
    const particles = new Float32Array(length * 3);
    for (let i = 0; i < length; i++) {
      let i3 = i * 3;
      particles[i3 + 0] = (i % size) / size;
      particles[i3 + 1] = i / size / size;
    }
    return particles;
  }, [size]);

  const uniforms = useMemo(() => ({
    uPositions: {
      value: null,
    }
  }), [])

  useFrame((state) => {
    const { gl, clock } = state;

    gl.setRenderTarget(renderTarget);
    gl.clear();
    gl.render(scene, camera);
    gl.setRenderTarget(null);

    points.current.material.uniforms.uPositions.value = renderTarget.texture;

    simulationMaterialRef.current.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <>
      {createPortal(
        <mesh>
          <simulationMaterial ref={simulationMaterialRef} args={[size]} />
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={positions.length / 3}
              array={positions}
              itemSize={3}
            />
            <bufferAttribute
              attach="attributes-uv"
              count={uvs.length / 2}
              array={uvs}
              itemSize={2}
            />
          </bufferGeometry>
        </mesh>,
        scene
      )}
      <points ref={points}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={particlesPosition.length / 3}
            array={particlesPosition}
            itemSize={3}
          />
        </bufferGeometry>
        <shaderMaterial
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          fragmentShader={fragmentShader}
          vertexShader={vertexShader}
          uniforms={uniforms}
        />
      </points>
    </>
  );
};

const Scene = () => {
  return (
    <Canvas camera={{ position: [1.5, 1.5, 2.5] }}>
      <ambientLight intensity={0.5} />
      <FBOParticles />
      <OrbitControls />
    </Canvas>
  );
};

export default Scene;
```

SimulationMaterial.js:

```

import simulationVertexShader from '!!raw-loader!./simulationVertexShader.glsl';
import simulationFragmentShader from '!!raw-loader!./simulationFragmentShader.glsl';
import * as THREE from "three";

const getRandomDataSphere = (width, height) => {
  // we need to create a vec4 since we're passing the positions to the fragment shader
  // data textures need to have 4 components, R, G, B, and A
  const length = width * height * 4 
  const data = new Float32Array(length);
    
  for (let i = 0; i < length; i++) {
    const stride = i * 4;

    const distance = Math.sqrt((Math.random())) * 2.0;
    const theta = THREE.MathUtils.randFloatSpread(360); 
    const phi = THREE.MathUtils.randFloatSpread(360); 

    data[stride] =  distance * Math.sin(theta) * Math.cos(phi)
    data[stride + 1] =  distance * Math.sin(theta) * Math.sin(phi);
    data[stride + 2] =  distance * Math.cos(theta);
    data[stride + 3] =  1.0; // this value will not have any impact
  }
  
  return data;
}

const getRandomDataBox = (width, height) => {
  var len = width * height * 4;
  var data = new Float32Array(len);

  for (let i = 0; i < data.length; i++) {
    const stride = i * 4;

    data[stride] = (Math.random() - 0.5) * 2.0;
    data[stride + 1] = (Math.random() - 0.5) * 2.0;
    data[stride + 2] = (Math.random() - 0.5) * 2.0;
    data[stride + 3] = 1.0;
  }
  return data;
};

class SimulationMaterial extends THREE.ShaderMaterial {
  constructor(size) {
    const positionsTextureA = new THREE.DataTexture(
      getRandomDataSphere(size, size),
      size,
      size,
      THREE.RGBAFormat,
      THREE.FloatType
    );
    positionsTextureA.needsUpdate = true;

    const positionsTextureB = new THREE.DataTexture(
      getRandomDataBox(size, size),
      size,
      size,
      THREE.RGBAFormat,
      THREE.FloatType
    );
    positionsTextureB.needsUpdate = true;

    const simulationUniforms = {
      positionsA: { value: positionsTextureA },
      positionsB: { value: positionsTextureB },
      uFrequency: { value: 0.25 },
      uTime: { value: 0 },
    };

    super({
      uniforms: simulationUniforms,
      vertexShader: simulationVertexShader,
      fragmentShader: simulationFragmentShader,
    });
  }
}

export default SimulationMaterial;

```

simulationVertexShader.js:

```
varying vec2 vUv;

void main() {
  vUv = uv;

  vec4 modelPosition = modelMatrix * vec4(position, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;
}
```

simulationFragmentShader.js:

```
uniform sampler2D positionsA;
uniform sampler2D positionsB;
uniform float uTime;
uniform float uFrequency;

varying vec2 vUv;

void main() {
  float time = abs(sin(uTime * 0.35));

  vec3 spherePositions = texture2D(positionsA, vUv).rgb;
  vec3 boxPositions = texture2D(positionsB, vUv).rgb;

  vec3 pos = mix(boxPositions, spherePositions, time);

  gl_FragColor = vec4(pos, 1.0);
}
```

vertexShader.js:

```
uniform sampler2D uPositions;
uniform float uTime;

void main() {
  vec3 pos = texture2D(uPositions, position.xy).xyz;

  vec4 modelPosition = modelMatrix * vec4(pos, 1.0);
  vec4 viewPosition = viewMatrix * modelPosition;
  vec4 projectedPosition = projectionMatrix * viewPosition;

  gl_Position = projectedPosition;

  gl_PointSize = 3.0;
  // Size attenuation;
  gl_PointSize *= step(1.0 - (1.0/64.0), position.x) + 0.5;
}
```

fragmentShader.js:

```
void main() {
  vec3 color = vec3(0.34, 0.53, 0.96);
  gl_FragColor = vec4(color, 1.0);
}
```

In it, I pass not only one but _two Data Textures_:

*   the first one contains the data to position the particles as a box
    
*   the second one as a sphere
    

Then in the fragment shader of the simulationMaterial, we use GLSL's mix function to alternate over time between the two "textures" which results in this scene where the particles morph from one shape to another.

Conclusion
----------

_From zero to FBO_, you now know pretty much everything I know about particles as of writing these words 🎉! There's, of course, still _a lot more_ to explore, but I hope this blog post was **a good introduction to the basics and more advanced techniques** and that it can serve as a guide to get back to during your own journey with Particles and React Three Fiber.

**Techniques like FBO enable almost limitless possibilities for particle-based scenes**, and I can't wait to see what you'll get to create with it ✨. I couldn't resist sharing this with you in this write-up 🪄. Frame Buffer Objects have a various set of use cases, not just limited to particles that I haven't explored deeply enough yet. That will probably be a topic for a future blog post, who knows?

As a productive next step to push your particle skills even further, I can only recommend to hack on your own. You now have all the tools to get started 😄.

Liked this article? Share it with a friend on [Bluesky](https://bsky.app/intent/compose?text=The magical world of Particles with React Three Fiber and Shaders by @maxime.bsky.social https://blog.maximeheckel.com/posts/the-magical-world-of-particles-with-react-three-fiber-and-shaders/) or [Twitter](https://twitter.com/intent/tweet?text=The magical world of Particles with React Three Fiber and Shaders by @MaximeHeckel https://blog.maximeheckel.com/posts/the-magical-world-of-particles-with-react-three-fiber-and-shaders/) or [support me](https://www.buymeacoffee.com/maximeheckel) to take on more ambitious projects to write about. Have a question, feedback or simply wish to contact me privately? [Shoot me a DM](http://twitter.com/MaximeHeckel) and I'll do my best to get back to you.

Have a wonderful day.

– Maxime