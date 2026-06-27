import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";

const ROOM = {
  width: 11,
  height: 4,
  depth: 8,
  wallThickness: 0.2,
  bladeThickness: 0.05,
  structuralThickness: 0.05,
};

const views = {
  indoor: { label: "室内", position: [0, 1.7, -4.2], target: [0, 1.8, 1.2] },
  outdoor: { label: "室外", position: [7.5, 2.6, 10], target: [0, 1.9, 0] },
  axonometric: { label: "轴测", position: [9, 7, 9], target: [0, 1.8, -2.2] },
  elevation: { label: "正视", position: [0, 2.2, 12], target: [0, 2, 0] },
};

const materialConfigs = {
  1: { color: 0x8a8a8a, roughness: 0.95, metalness: 0.05 },
  2: { color: 0xd0d4d8, roughness: 0.35, metalness: 0.65 },
  3: { color: 0x6a6e72, roughness: 0.15, metalness: 0.85 },
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function mmToMeters(value, fallback) {
  return numberOr(value, fallback * 1000) / 1000;
}

function divideInclusive(start, end, spacing) {
  const points = [];
  const step = Math.max(Math.abs(spacing), 0.05);
  const epsilon = 0.0001;

  for (let value = start; value < end - epsilon; value += step) {
    points.push(Number(value.toFixed(4)));
    if (points.length > 1000) break;
  }

  if (!points.length || Math.abs(points[points.length - 1] - end) > epsilon) {
    points.push(Number(end.toFixed(4)));
  }

  return points;
}

function makeShadingMaterial(materialKey) {
  const cfg = materialConfigs[materialKey] || materialConfigs[2];
  return new THREE.MeshStandardMaterial({
    color: cfg.color,
    roughness: cfg.roughness,
    metalness: cfg.metalness,
  });
}

function addBox(scene, size, position, material, rotation = {}) {
  if (size.some((value) => value <= 0)) return null;

  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
  mesh.position.set(...position);
  mesh.rotation.set(rotation.x || 0, rotation.y || 0, rotation.z || 0);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  scene.add(mesh);
  return mesh;
}

function applyCameraView(camera, controls, view) {
  const next = views[view];
  camera.position.set(...next.position);
  controls.target.set(...next.target);
  controls.update();
}

const ThreeDViewer = forwardRef(function ThreeDViewer({ params = {}, activeView, onViewChange }, ref) {
  const mountRef = useRef(null);
  const rendererRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const [view, setView] = useState(activeView || "outdoor");
  const currentView = activeView || view;

  useImperativeHandle(ref, () => ({
    capture: () => {
      if (!rendererRef.current || !sceneRef.current || !cameraRef.current) return "";
      rendererRef.current.render(sceneRef.current, cameraRef.current);
      return rendererRef.current.domElement.toDataURL("image/png");
    },
    captureView: (nextView) => {
      if (!rendererRef.current || !sceneRef.current || !cameraRef.current || !controlsRef.current) return "";
      applyCameraView(cameraRef.current, controlsRef.current, nextView || currentView);
      rendererRef.current.render(sceneRef.current, cameraRef.current);
      return rendererRef.current.domElement.toDataURL("image/png");
    },
  }), [currentView]);

  useEffect(() => {
    const mount = mountRef.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf4f7f6);
    sceneRef.current = scene;

    const initialWidth = Math.max(mount.clientWidth, 1);
    const initialHeight = Math.max(mount.clientHeight, 1);
    const camera = new THREE.PerspectiveCamera(45, initialWidth / initialHeight, 0.1, 100);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(initialWidth, initialHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    rendererRef.current = renderer;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controlsRef.current = controls;
    applyCameraView(camera, controls, currentView);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f86, 1.9));
    const sun = new THREE.DirectionalLight(0xffffff, 2.4);
    sun.position.set(7, 8, 9);
    sun.castShadow = true;
    scene.add(sun);

    const wallMaterial = new THREE.MeshStandardMaterial({ color: 0xdce3dd, roughness: 0.85 });
    const floorMaterial = new THREE.MeshStandardMaterial({ color: 0xc8cfc8, roughness: 0.9 });
    const ceilingMaterial = new THREE.MeshStandardMaterial({ color: 0xeef2ef, roughness: 0.82 });
    const structureMaterial = new THREE.MeshStandardMaterial({ color: 0xbcc5bd, roughness: 0.88 });

    const facadeZ = 0;
    const wallCenterZ = facadeZ - ROOM.wallThickness / 2;
    const roomCenterZ = -ROOM.depth / 2;
    const halfWidth = ROOM.width / 2;

    addBox(scene, [ROOM.width + ROOM.wallThickness * 2, ROOM.wallThickness, ROOM.depth], [0, -ROOM.wallThickness / 2, roomCenterZ], floorMaterial);
    addBox(scene, [ROOM.width + ROOM.wallThickness * 2, ROOM.wallThickness, ROOM.depth], [0, ROOM.height + ROOM.wallThickness / 2, roomCenterZ], ceilingMaterial);
    addBox(scene, [ROOM.wallThickness, ROOM.height, ROOM.depth], [-halfWidth - ROOM.wallThickness / 2, ROOM.height / 2, roomCenterZ], wallMaterial);
    addBox(scene, [ROOM.wallThickness, ROOM.height, ROOM.depth], [halfWidth + ROOM.wallThickness / 2, ROOM.height / 2, roomCenterZ], wallMaterial);
    addBox(scene, [ROOM.width + ROOM.wallThickness * 2, ROOM.height, ROOM.wallThickness], [0, ROOM.height / 2, -ROOM.depth - ROOM.wallThickness / 2], wallMaterial);

    const wwr = clamp(numberOr(params.wwr, 50) / 100, 0.05, 0.9);
    const windowScale = Math.sqrt(wwr);
    const windowWidth = ROOM.width * windowScale;
    const windowHeight = ROOM.height * windowScale;
    const windowBottom = (ROOM.height - windowHeight) / 2;
    const windowTop = windowBottom + windowHeight;
    const windowCenterY = ROOM.height / 2;
    const sideFrameWidth = (ROOM.width - windowWidth) / 2;

    addBox(scene, [ROOM.width, ROOM.height - windowTop, ROOM.wallThickness], [0, windowTop + (ROOM.height - windowTop) / 2, wallCenterZ], wallMaterial);
    addBox(scene, [ROOM.width, windowBottom, ROOM.wallThickness], [0, windowBottom / 2, wallCenterZ], wallMaterial);
    addBox(scene, [sideFrameWidth, windowHeight, ROOM.wallThickness], [-halfWidth + sideFrameWidth / 2, windowCenterY, wallCenterZ], wallMaterial);
    addBox(scene, [sideFrameWidth, windowHeight, ROOM.wallThickness], [halfWidth - sideFrameWidth / 2, windowCenterY, wallCenterZ], wallMaterial);

    const glass = new THREE.Mesh(
      new THREE.BoxGeometry(windowWidth, windowHeight, 0.04),
      new THREE.MeshPhysicalMaterial({
        color: 0x76a8bd,
        transmission: 0.25,
        transparent: true,
        opacity: 0.55,
        roughness: 0.05,
      })
    );
    glass.position.set(0, windowCenterY, facadeZ + 0.02);
    scene.add(glass);

    const materialKey = Number(params.material) || 2;
    const shadingMaterial = makeShadingMaterial(materialKey);
    const spacing = Math.max(mmToMeters(params.spacing, 0.6), 0.05);
    const bladeDepth = Math.max(mmToMeters(params.blade_depth, 0.2), 0.02);
    const wallDistance = Math.max(mmToMeters(params.window_distance, 0.1), 0);
    const bladeCenterZ = facadeZ + wallDistance + bladeDepth / 2;
    const shadingType = Number(params.shading_type) || 1;
    const hRotation = THREE.MathUtils.degToRad(numberOr(params.h_rotation, 0));
    const vRotation = THREE.MathUtils.degToRad(numberOr(params.v_rotation, 0));

    if (shadingType === 1 || shadingType === 3) {
      divideInclusive(0, ROOM.height, spacing).forEach((y) => {
        addBox(
          scene,
          [ROOM.width, ROOM.bladeThickness, bladeDepth],
          [0, y, bladeCenterZ],
          shadingMaterial,
          { x: hRotation }
        );
      });
    }

    if (shadingType === 2 || shadingType === 3) {
      divideInclusive(-halfWidth, halfWidth, spacing).forEach((x) => {
        addBox(
          scene,
          [ROOM.bladeThickness, ROOM.height, bladeDepth],
          [x, ROOM.height / 2, bladeCenterZ],
          shadingMaterial,
          { y: vRotation }
        );
      });
    }

    const horizontalDepth = Math.max(mmToMeters(params.horizontal_depth, 0.3), 0);
    addBox(
      scene,
      [ROOM.width, ROOM.structuralThickness, horizontalDepth],
      [0, ROOM.height - ROOM.structuralThickness / 2, facadeZ + horizontalDepth / 2],
      structureMaterial
    );

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(18, 18),
      new THREE.MeshStandardMaterial({ color: 0xbec8be, roughness: 1 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, -0.012, -2.5);
    ground.receiveShadow = true;
    scene.add(ground);

    let frame = null;
    function animate() {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);

    function resize() {
      const width = Math.max(mount.clientWidth, 1);
      const height = Math.max(mount.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    }
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    window.addEventListener("resize", resize);
    resize();

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      resizeObserver.disconnect();
      controls.dispose();
      scene.traverse((object) => {
        object.geometry?.dispose();
      });
      const materials = new Set();
      scene.traverse((object) => {
        if (Array.isArray(object.material)) {
          object.material.forEach((material) => materials.add(material));
        } else if (object.material) {
          materials.add(object.material);
        }
      });
      materials.forEach((material) => material.dispose());
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
      renderer.dispose();
      sceneRef.current = null;
    };
  }, [params]);

  useEffect(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    applyCameraView(camera, controls, currentView);
  }, [currentView]);

  function selectView(nextView) {
    if (onViewChange) {
      onViewChange(nextView);
      return;
    }
    setView(nextView);
  }

  return (
    <div className="viewer-wrap">
      <div className="view-tabs">
        {Object.entries(views).map(([id, item]) => (
          <button className={id === currentView ? "active" : ""} key={id} onClick={() => selectView(id)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="viewer" ref={mountRef} />
    </div>
  );
});

export default ThreeDViewer;
