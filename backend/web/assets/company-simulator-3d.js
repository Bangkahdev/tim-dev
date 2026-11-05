let THREE;
try {
  THREE = await import('https://cdn.jsdelivr.net/npm/three@0.187.0/build/three.module.js');
} catch (error) {
  const status = document.getElementById('sim3dConnection');
  if (status) status.textContent = 'THREE.JS GAGAL DIMUAT · PERIKSA INTERNET';
  console.error('Bangkah 3D Simulator: gagal memuat Three.js dari CDN.', error);
}

if (THREE) (() => {
  'use strict';

  const canvas = document.getElementById('company3dCanvas');
  const stage = document.getElementById('sim3dStage');
  if (!canvas || !stage) return;

  const $ = (selector) => document.querySelector(selector);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const distance2 = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
  const clock = new THREE.Clock();
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#b9cbd2');
  scene.fog = new THREE.Fog('#b9cbd2', 62, 118);

  const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 180);
  camera.position.set(0, 4, 9);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const hemi = new THREE.HemisphereLight(0xe9f4ff, 0x7b7869, 2.1);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff3df, 2.35);
  sun.position.set(-24, 36, 24);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -42;
  sun.shadow.camera.right = 42;
  sun.shadow.camera.top = 42;
  sun.shadow.camera.bottom = -42;
  sun.shadow.normalBias = 0.035;
  scene.add(sun);

  const materials = {};
  const mat = (color, roughness = 0.82, metalness = 0) => {
    const key = `${color}|${roughness}|${metalness}`;
    if (!materials[key]) materials[key] = new THREE.MeshStandardMaterial({ color, roughness, metalness });
    return materials[key];
  };
  const glassMat = new THREE.MeshPhysicalMaterial({ color: 0xb8d4dc, roughness: 0.13, metalness: 0.05, transmission: 0.12, transparent: true, opacity: 0.34, side: THREE.DoubleSide });
  const obstacleBoxes = [];
  const world = new THREE.Group();
  scene.add(world);

  function addBox(parent, x, y, z, w, h, d, material, options = {}) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    mesh.castShadow = options.castShadow !== false;
    mesh.receiveShadow = options.receiveShadow !== false;
    if (options.rotation) mesh.rotation.y = options.rotation;
    parent.add(mesh);
    if (options.collide) obstacleBoxes.push({ minX: x - w / 2, maxX: x + w / 2, minZ: z - d / 2, maxZ: z + d / 2 });
    return mesh;
  }

  function addCylinder(parent, x, y, z, radiusTop, radiusBottom, height, material, radialSegments = 16) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, radialSegments), material);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }

  function addSphere(parent, x, y, z, radius, material, scale = [1, 1, 1]) {
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 18, 14), material);
    mesh.position.set(x, y, z);
    mesh.scale.set(...scale);
    mesh.castShadow = true;
    parent.add(mesh);
    return mesh;
  }

  function addLabel(text, x, y, z, tint = '#edf2ec') {
    const c = document.createElement('canvas');
    c.width = 512; c.height = 128;
    const ctx = c.getContext('2d');
    ctx.fillStyle = 'rgba(29,43,43,.78)';
    ctx.beginPath(); ctx.roundRect(8, 8, 496, 112, 24); ctx.fill();
    ctx.fillStyle = tint;
    ctx.font = '700 35px Arial';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(text.toUpperCase(), 256, 64, 455);
    const texture = new THREE.CanvasTexture(c);
    texture.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
    sprite.position.set(x, y, z);
    sprite.scale.set(4.3, 1.08, 1);
    world.add(sprite);
    return sprite;
  }

  // Exterior grounds and the large cutaway office shell.
  addBox(world, 0, -0.42, 0, 150, 0.65, 150, mat('#839a7d'), { collide: false });
  addBox(world, 0, -0.06, 0, 64, 0.28, 56, mat('#b8b8ad'), { collide: false });
  addBox(world, 0, 0.11, 0, 62, 0.08, 54, mat('#d9d6c9'), { collide: false });

  // Modular floor panels make the departments legible without turning the building into a maze.
  const roomDefs = [
    { id: 'manager', name: 'Lead Manager', x: -20, z: -15, w: 19, d: 14, color: '#dfe9dc' },
    { id: 'planning', name: 'Project Management', x: 0, z: -15, w: 19, d: 14, color: '#e8e5f1' },
    { id: 'architect', name: 'System Architecture', x: 20, z: -15, w: 19, d: 14, color: '#e4eaf0' },
    { id: 'frontend', name: 'Frontend Studio', x: -20, z: 0, w: 19, d: 14, color: '#e9e6dc' },
    { id: 'qa', name: 'Quality Assurance', x: 0, z: 0, w: 19, d: 14, color: '#e2ecea' },
    { id: 'backend', name: 'Backend Engineering', x: 20, z: 0, w: 19, d: 14, color: '#e8e7de' },
    { id: 'meeting', name: 'Meeting Room', x: -20, z: 14, w: 19, d: 12, color: '#e6e4ef' },
    { id: 'api', name: 'API Studio', x: 20, z: 14, w: 19, d: 12, color: '#e2e9dd' }
  ];
  roomDefs.forEach((r) => {
    addBox(world, r.x, 0.105, r.z, r.w, 0.035, r.d, mat(r.color), { collide: false, castShadow: false });
    addLabel(r.name, r.x, 2.95, r.z - r.d / 2 + 1.4, '#f2f4ef');
  });

  // Perimeter walls are deliberately low/cutaway so the third-person camera can see the full office.
  const wall = mat('#d9ded8');
  const trim = mat('#879a91');
  const outsideGlass = new THREE.MeshStandardMaterial({ color: 0xaac8d2, roughness: 0.18, metalness: 0.05, transparent: true, opacity: 0.42 });
  addBox(world, -32, 1.45, 0, 0.35, 2.9, 56, wall, { collide: true });
  addBox(world, 32, 1.45, 0, 0.35, 2.9, 56, wall, { collide: true });
  addBox(world, 0, 1.45, -28, 64, 2.9, 0.35, wall, { collide: true });
  addBox(world, -18, 1.45, 28, 28, 2.9, 0.35, wall, { collide: true });
  addBox(world, 18, 1.45, 28, 28, 2.9, 0.35, wall, { collide: true });
  // Entrance frame with a wide doorway and glass panels.
  addBox(world, -3.25, 1.45, 28, 0.25, 2.9, 0.35, trim, { collide: true });
  addBox(world, 3.25, 1.45, 28, 0.25, 2.9, 0.35, trim, { collide: true });
  addBox(world, 0, 2.72, 28, 6.2, 0.26, 0.35, trim, { collide: true });
  addBox(world, -13, 1.5, 27.78, 8, 2.4, 0.08, outsideGlass, { collide: false });
  addBox(world, 13, 1.5, 27.78, 8, 2.4, 0.08, outsideGlass, { collide: false });

  // Glass partitions and door gaps between departments.
  function glassPartition(x1, z1, x2, z2, gapCenter = null, gap = 2.8) {
    const length = Math.hypot(x2 - x1, z2 - z1);
    const horizontal = Math.abs(z2 - z1) < 0.01;
    const cx = (x1 + x2) / 2, cz = (z1 + z2) / 2;
    const addSeg = (start, end) => {
      const mid = (start + end) / 2, len = end - start;
      if (len <= 0.5) return;
      if (horizontal) addBox(world, mid, 1.22, cz, len, 2.42, 0.12, glassMat, { collide: true });
      else addBox(world, cx, 1.22, mid, 0.12, 2.42, len, glassMat, { collide: true });
    };
    if (gapCenter === null) { addSeg(0, length); return; }
    const gapStart = clamp(gapCenter - gap / 2, 0, length), gapEnd = clamp(gapCenter + gap / 2, 0, length);
    addSeg(0, gapStart); addSeg(gapEnd, length);
  }
  // North and middle office rows.
  glassPartition(-30, -8, 30, -8, 30, 3.4);
  glassPartition(-30, 7, 30, 7, 30, 4.0);
  glassPartition(-10, -28, -10, 7, 17.4, 3.0);
  glassPartition(10, -28, 10, 7, 17.4, 3.0);
  // Meeting room and API studio divisions.
  glassPartition(-30, 20, -10, 20, 10, 3.0);
  glassPartition(10, 20, 30, 20, 10, 3.0);

  // Windows, mullions, light fixtures and room decor.
  for (const z of [-27.75, -18.5, -5.5, 9.5, 26.8]) {
    [-23, -16, -3, 4, 16, 23].forEach((x) => {
      if (z === 26.8 && Math.abs(x) < 5) return;
      addBox(world, x, 2.0, z, 2.3, 1.25, 0.08, outsideGlass, { castShadow: false, collide: false });
      addBox(world, x, 2.65, z, 2.42, 0.08, 0.12, trim, { castShadow: false, collide: false });
    });
  }
  for (const [x, z] of [[-20,-15],[0,-15],[20,-15],[-20,0],[0,0],[20,0],[-20,14],[20,14],[0,17]]) {
    addBox(world, x, 2.72, z, 4.2, 0.12, 0.5, mat('#f2ead8', 0.4), { castShadow: false, collide: false });
    const lamp = new THREE.PointLight(0xffedcf, 0.52, 10, 2);
    lamp.position.set(x, 2.35, z); world.add(lamp);
  }

  // Outdoor entrance approach, trees, planters and company sign.
  addBox(world, 0, -0.03, 35, 14, 0.12, 12, mat('#bfc2b9'), { collide: false });
  addBox(world, 0, 1.45, 28.05, 8.2, 0.3, 0.28, mat('#415a50'), { collide: false });
  addLabel('Bangkah Headquarters', 0, 3.8, 28, '#ffffff').scale.set(6.2, 1.2, 1);
  function addTree(x, z, size = 1) {
    addCylinder(world, x, 0.85 * size, z, 0.22 * size, 0.3 * size, 1.7 * size, mat('#795f48'));
    addSphere(world, x, 2.0 * size, z, 1.15 * size, mat('#6f9474'), [1.15, 1.05, 1.0]);
    addSphere(world, x + .55 * size, 2.2 * size, z - .15 * size, .72 * size, mat('#86a985'));
  }
  [[-40,18],[-37,-13],[39,18],[39,-18],[-35,37],[35,38]].forEach(([x,z],i)=>addTree(x,z,i%2?0.8:1));
  for (const x of [-8, 8]) {
    addBox(world, x, .28, 31, 3.2, .55, 1.0, mat('#7b8d7d'), { collide: true });
    [-.8,0,.8].forEach((dx)=>addSphere(world, x+dx, .85, 31, .55, mat('#789873'), [1,1.35,1]));
  }

  function addPlant(x, z, scale = 1) {
    addCylinder(world, x, .35 * scale, z, .35 * scale, .42 * scale, .65 * scale, mat('#b98d6d'));
    for (let i=0;i<5;i++) {
      const leaf=addSphere(world, x + Math.cos(i*1.25)*.28*scale, .95*scale + (i%2)*.18*scale, z + Math.sin(i*1.25)*.28*scale, .25*scale, mat(i%2?'#6e9676':'#86a783'), [0.65,1.5,0.65]);
      leaf.rotation.z = Math.cos(i*1.25)*.4;
    }
  }

  // Office furniture helpers.
  function addChair(x, z, rotation = 0, color = '#657d79') {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rotation; world.add(g);
    addBox(g, 0, .58, 0, .9, .16, .88, mat(color), { collide: false });
    addBox(g, 0, .98, -.38, .88, .78, .14, mat(color), { collide: false });
    addCylinder(g, 0, .28, 0, .11, .11, .42, mat('#596761'));
    for(let i=0;i<4;i++){const a=i*Math.PI/2;addBox(g,Math.cos(a)*.35,.1,Math.sin(a)*.35,.58,.08,.08,mat('#78817b'),{rotation:-a,collide:false})}
    return g;
  }
  function addDesk(x, z, rotation = 0, chair = true) {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rotation; world.add(g);
    addBox(g, 0, .78, 0, 2.7, .16, 1.35, mat('#b9926e'), { collide: false });
    for (const [dx,dz] of [[-1.15,-.48],[1.15,-.48],[-1.15,.48],[1.15,.48]]) addBox(g,dx,.38,dz,.12,.75,.12,mat('#806a54'),{collide:false});
    addBox(g, 0, 1.35, -.36, .98, .76, .10, mat('#34454c'), { collide: false });
    addBox(g, 0, 1.36, -.295, .84, .57, .025, mat('#9eb9b1'), { collide: false });
    addBox(g, -.02, 1.0, -.34, .1, .18, .12, mat('#697b76'), { collide: false });
    addBox(g, 0, .89, .27, .76, .045, .3, mat('#6b7772'), { collide: false });
    addBox(g, .75, .87, .2, .2, .055, .2, mat('#3a4242'), { collide: false });
    addCylinder(g, -1.0, .92, .32, .09, .09, .18, mat('#eee9dd'));
    if (chair) addChair(0, 1.35, Math.PI, '#72877f');
    obstacleBoxes.push({ minX:x-1.48,maxX:x+1.48,minZ:z-.78,maxZ:z+.78 });
    return { x, z, group:g, seat:{x:x,z:z+1.55} };
  }
  function addMeetingTable(x,z) {
    const g=new THREE.Group();g.position.set(x,0,z);world.add(g);
    addCylinder(g,0,.76,0,2.75,2.75,.18,mat('#a98462'),36);
    for(let i=0;i<6;i++){const a=i*Math.PI/3;addCylinder(g,Math.cos(a)*1.9,.38,Math.sin(a)*1.9,.07,.09,.76,mat('#7e6a55'));
      addChair(x+Math.cos(a)*3.25,z+Math.sin(a)*3.25,Math.atan2(-Math.cos(a),Math.sin(a)),'#718b83');}
    addBox(g,0,.9,-.8,1.05,.07,.55,mat('#303c43'),{collide:false});
    addBox(g,0,.95,-.8,.91,.025,.43,mat('#9cb5ae'),{collide:false});
    obstacleBoxes.push({minX:x-2.9,maxX:x+2.9,minZ:z-2.9,maxZ:z+2.9});
    return g;
  }

  // Dedicated desks for every AI employee.
  const stationByEmployee = {
    lead: { x:-21, z:-14.5, room:'manager' },
    coo: { x:-1, z:-14.5, room:'planning' },
    architect: { x:20, z:-14.5, room:'architect' },
    frontend: { x:-21, z:-1, room:'frontend' },
    qa: { x:-1, z:-1, room:'qa' },
    backend: { x:20, z:-1, room:'backend' },
    api: { x:20, z:12, room:'api' }
  };
  const desks = {};
  Object.entries(stationByEmployee).forEach(([id,p])=>{desks[id]=addDesk(p.x,p.z,0,true);});
  // Extra shared workstations make each department look staffed and usable.
  [[-24,-10],[-17,-10],[-4,-10],[3,-10],[16,-10],[24,-10],[-24,3],[-17,3],[-4,3],[3,3],[16,3],[24,3],[16,15],[24,15]].forEach(([x,z])=>addDesk(x,z,Math.PI,true));

  // Meeting room: long table, chairs, screen and wall-mounted whiteboard.
  addMeetingTable(-20, 13);
  addBox(world,-20,2.15,7.85,5.4,2.5,.18,mat('#42535a'),{collide:true});
  addBox(world,-20,2.18,7.72,4.8,2.1,.03,mat('#b6cbc6'),{collide:false});
  addBox(world,-25,1.25,17.8,3,.08,.5,mat('#9eac9e'),{collide:false});

  // Reception and public lobby immediately inside the main entrance.
  addBox(world,0,.8,18.4,7.8,1.55,1.55,mat('#92785f'),{collide:true});
  addBox(world,0,1.62,18.4,8.05,.13,1.7,mat('#d2b99a'),{collide:false});
  addBox(world,0,1.68,17.78,2.1,.07,.52,mat('#2f3c42'),{collide:false});
  addBox(world,0,1.73,17.75,1.85,.025,.4,mat('#a7c1ba'),{collide:false});
  addCylinder(world,2.8,1.72,18.4,.13,.13,.1,mat('#d8c18d'));
  addChair(-5.2,18.4,0,'#78928a'); addChair(5.2,18.4,Math.PI,'#78928a');
  addBox(world,-5.2,.8,16.3,2.9,1.1,.95,mat('#9b9a8c'),{collide:true});
  addBox(world,5.2,.8,16.3,2.9,1.1,.95,mat('#9b9a8c'),{collide:true});
  addBox(world,0,.45,14.3,3.4,.5,1.8,mat('#b99a7a'),{collide:true});
  addPlant(-8,21,1.15); addPlant(8,21,1.15);
  addLabel('Reception · Visitor Check-in',0,3.1,18.1,'#f7f3e9');

  // Pantry, coffee counter and storage.
  addBox(world,22,.72,20,8,1.4,1.35,mat('#a9a18e'),{collide:true});
  addBox(world,22,1.46,20,8.2,.12,1.5,mat('#e0d4c0'),{collide:false});
  addBox(world,19,1.75,19.7,.75,.55,.55,mat('#46595a'),{collide:false});
  addBox(world,19,2.04,19.39,.5,.07,.05,mat('#b7cbc4'),{collide:false});
  addCylinder(world,22.5,1.65,19.7,.22,.22,.18,mat('#eee8db'));
  addCylinder(world,23.3,1.65,19.7,.22,.22,.18,mat('#eee8db'));
  addBox(world,24.5,1.8,19.7,1.3,.4,.8,mat('#536e66'),{collide:false});
  addLabel('Pantry & Coffee',22,3.1,18.3,'#f7f3e9');

  // Lounge and library archive.
  addBox(world,-23,.68,21,5.4,1.1,1.45,mat('#879c91'),{collide:true});
  addBox(world,-23,1.22,20.45,5.3,.15,.28,mat('#a9b8a9'),{collide:false});
  addBox(world,-23,.55,17.4,3.4,.65,1.7,mat('#b79a7d'),{collide:true});
  addBox(world,-23,.92,17.4,3.3,.12,1.6,mat('#d2b895'),{collide:false});
  addBox(world,-28,1.5,-22,1.1,3.0,5.4,mat('#987c5f'),{collide:true});
  for(let shelf=0;shelf<3;shelf++){
    addBox(world,-27.4,.7+shelf*.85,-22, .13,.12,4.9,mat('#d3b58d'),{collide:false});
    for(let b=0;b<8;b++) addBox(world,-27.38,.98+shelf*.85,-24.1+b*.58,.22,.48,.38,mat(['#748d82','#c58f74','#7b89a8','#bdad75'][b%4]),{collide:false});
  }
  addLabel('Company Archive',-24.2,3.55,-22,'#f7f3e9');
  addPlant(-28,19,1.0); addPlant(28,22,1.0); addPlant(-8,-22,.9); addPlant(8,-22,.9);

  // Shared wall art, notice board and printer corner.
  addBox(world,-8,1.85,-2.8,.12,2.2,3.2,mat('#927a63'),{collide:false});
  addBox(world,-7.9,1.85,-2.8,.035,1.8,2.8,mat('#d9e3d7'),{collide:false});
  addBox(world,8,1.85,3.7,.12,2.1,3.0,mat('#8f9c92'),{collide:false});
  addBox(world,8.1,1.9,3.7,.05,1.7,2.6,mat('#e5e9e3'),{collide:false});
  addBox(world,8.8,.68,5.3,1.1,1.3,1.1,mat('#d4d8d7'),{collide:true});
  addBox(world,8.8,1.4,5.3,.9,.1,.9,mat('#899894'),{collide:false});
  addLabel('Print & Supplies',8.8,2.65,4.5,'#f5f4ea');

  // Warm point lights make the interior read as an occupied workplace.
  [[-20,-15],[0,-15],[20,-15],[-20,0],[0,0],[20,0],[-20,14],[20,14],[0,19]].forEach(([x,z])=>{
    const light=new THREE.PointLight(0xffe6c5,.62,12,2);light.position.set(x,2.5,z);world.add(light);
  });

  const statusNames = { working:'Bekerja', talking:'Berbicara', listening:'Mendengarkan', completed:'Selesai', failed:'Perlu perhatian', blocked:'Terhambat', idle:'Menunggu instruksi' };
  const roster = [
    {id:'lead',name:'Arman',role:'Lead Manager',shirt:'#536f5e',pants:'#35434a',skin:'#c78f70',hair:'#2c2928',accent:'#d3b98b'},
    {id:'coo',name:'Sinta',role:'COO / Project Manager',shirt:'#7e799e',pants:'#42414f',skin:'#e0b696',hair:'#3c2d2a',accent:'#cbb7df'},
    {id:'architect',name:'Raka',role:'System Architect',shirt:'#577f91',pants:'#343e4a',skin:'#d5a786',hair:'#2d2925',accent:'#9bb7c0'},
    {id:'backend',name:'Bima',role:'Backend Developer',shirt:'#547d79',pants:'#3e4646',skin:'#a87356',hair:'#282321',accent:'#adc6be'},
    {id:'api',name:'Naya',role:'API Specialist',shirt:'#a67867',pants:'#49434a',skin:'#e1b497',hair:'#40322d',accent:'#d9bfa8'},
    {id:'frontend',name:'Dira',role:'Frontend Developer',shirt:'#927aa4',pants:'#45404d',skin:'#efc5a6',hair:'#3f302c',accent:'#d8c6e5'},
    {id:'qa',name:'Tika',role:'QA Engineer',shirt:'#8b895a',pants:'#46453b',skin:'#956044',hair:'#2e2622',accent:'#d5d0a3'},
    {id:'reception',name:'Mira',role:'Front Desk · Receptionist',shirt:'#728c86',pants:'#4a5250',skin:'#d7aa8a',hair:'#342a29',accent:'#b6d1c4',receptionist:true}
  ];

  function labelTexture(text, color = '#f7f8f6') {
    const c=document.createElement('canvas');c.width=512;c.height=128;const ctx=c.getContext('2d');
    ctx.fillStyle='rgba(24,34,36,.82)';ctx.beginPath();ctx.roundRect(6,8,500,112,22);ctx.fill();
    ctx.fillStyle=color;ctx.font='700 34px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,256,63,470);
    const tex=new THREE.CanvasTexture(c);tex.colorSpace=THREE.SRGBColorSpace;return tex;
  }
  function makeCharacter(config, isPlayer = false) {
    const root = new THREE.Group();
    const body = new THREE.Group(); root.add(body);
    const shirt = mat(config.shirt, .86), pants = mat(config.pants, .9), skin = mat(config.skin, .88), hair = mat(config.hair, .92);
    const shoes = mat('#293234'), belt = mat('#313b3e'), white = mat('#f4eee2');
    const groundShadow = new THREE.Mesh(new THREE.CircleGeometry(.52,24),new THREE.MeshBasicMaterial({color:0x26312e,transparent:true,opacity:.2,depthWrite:false}));
    groundShadow.rotation.x=-Math.PI/2;groundShadow.position.y=.018;root.add(groundShadow);
    // Legs and feet, with pivot groups for a visible walk cycle.
    const legs=[];
    for(const side of [-1,1]){
      const pivot=new THREE.Group();pivot.position.set(side*.19,.82,0);body.add(pivot);legs.push(pivot);
      const leg=new THREE.Mesh(new THREE.CapsuleGeometry(.13,.55,4,8),pants);leg.position.y=-.32;leg.castShadow=true;pivot.add(leg);
      const foot=addBox(pivot,0,-.69,-.1,.28,.17,.48,shoes,{collide:false});
      foot.position.x=0;
    }
    const torso=addBox(body,0,1.18,0,.75,.88,.4,shirt,{collide:false});torso.geometry.dispose();torso.geometry=new THREE.CapsuleGeometry(.36,.45,5,10);torso.position.y=1.2;
    addBox(body,0,.88,0,.57,.22,.34,belt,{collide:false});
    addCylinder(body,0,1.67,0,.12,.13,.2,skin,12);
    addSphere(body,0,1.99,0,.36,skin,[.88,1.08,.82]);
    // Hair cap and back hair.
    addSphere(body,0,2.2,.025,.31,hair,[1.02,.55,.98]);
    addBox(body,0,1.95,.29,.43,.23,.1,hair,{collide:false});
    addSphere(body,-.31,2.02,.02,.12,hair,[.55,1.2,.8]);
    addSphere(body,.31,2.02,.02,.12,hair,[.55,1.2,.8]);
    // Face details look toward local -Z.
    addSphere(body,-.11,2.02,-.295,.027,mat('#293330'),[1,1,.42]);
    addSphere(body,.11,2.02,-.295,.027,mat('#293330'),[1,1,.42]);
    addBox(body,0,1.9,-.29,.09,.025,.025,mat('#986b58'),{collide:false});
    const arms=[];
    for(const side of [-1,1]){
      const pivot=new THREE.Group();pivot.position.set(side*.43,1.48,0);body.add(pivot);arms.push(pivot);
      const upper=new THREE.Mesh(new THREE.CapsuleGeometry(.105,.43,4,8),shirt);upper.position.y=-.25;upper.rotation.z=side*.12;upper.castShadow=true;pivot.add(upper);
      const fore=new THREE.Mesh(new THREE.CapsuleGeometry(.085,.38,4,8),skin);fore.position.set(0,-.65,-.025);fore.castShadow=true;pivot.add(fore);
      addSphere(pivot,0,-.87,-.03,.1,skin,[.95,1,.9]);
    }
    const badge=addBox(body,.22,1.4,-.205,.13,.14,.025,mat(config.accent||'#d5d9cd'),{collide:false});
    const nameSprite=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture(isPlayer?'OWNER · ANDA':config.name),transparent:true,depthWrite:false}));
    nameSprite.position.set(0,2.78,0);nameSprite.scale.set(isPlayer?2.35:2.05,.52,1);root.add(nameSprite);
    const activitySprite=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture(isPlayer?'COMPANY OWNER':'MENUNGGU INSTRUKSI','#dce9dd'),transparent:true,depthWrite:false}));
    activitySprite.position.set(0,2.38,0);activitySprite.scale.set(isPlayer?1.95:1.9,.40,1);root.add(activitySprite);
    let speech=null;
    const npc={config,root,body,arms,legs,home: new THREE.Vector3(),target:null,path:[],pathIndex:0,walkSpeed:2.0,state:'idle',phase:Math.random()*6,
      routineAt:performance.now()+9000+Math.random()*18000,routineIndex:0,bubble:null,lastRoom:null,record:null,groundShadow, nameSprite, speech, isPlayer,
      setPosition(x,z){root.position.set(x,0,z);},
      setSpeech(message){if(this.bubble){root.remove(this.bubble);this.bubble.material.map.dispose();this.bubble.material.dispose();this.bubble=null;}if(!message)return;const tex=labelTexture(message.length>76?message.slice(0,73)+'…':message,'#ffffff');this.bubble=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false}));this.bubble.position.set(0,3.48,0);this.bubble.scale.set(3.7,.92,1);root.add(this.bubble);}
    };
    npc.meshes={torso,arms,legs,badge};
    root.userData.character=npc;
    return npc;
  }

  const player = makeCharacter({id:'owner',name:'Owner',role:'Company Owner',shirt:'#b88462',pants:'#35454c',skin:'#d5a17f',hair:'#302723',accent:'#d6b78d'},true);
  player.root.position.set(0,0,25.1);
  player.root.rotation.y = 0;
  world.add(player.root);
  const npcs = new Map();
  const agentConfigs = roster.filter(x=>!x.receptionist);
  agentConfigs.forEach((config)=>{
    const npc=makeCharacter(config);
    const station=stationByEmployee[config.id];
    npc.home.set(station.x,0,station.z+1.6);
    npc.setPosition(npc.home.x,npc.home.z);
    npc.root.rotation.y=0;
    npc.record={id:config.id,name:config.name,role:config.role,status:'idle',room_id:station.room};
    world.add(npc.root);npcs.set(config.id,npc);
  });
  const receptionistConfig=roster.find(x=>x.receptionist);
  const receptionist=makeCharacter(receptionistConfig);
  receptionist.setPosition(0,0,16.25);receptionist.root.rotation.y=Math.PI;
  receptionist.state='greeting';receptionist.routineAt=performance.now()+5000;
  world.add(receptionist.root);

  const roomCenters = {
    manager:{x:-20,z:-15},planning:{x:0,z:-15},architect:{x:20,z:-15},
    frontend:{x:-20,z:0},qa:{x:0,z:0},backend:{x:20,z:0},
    meeting:{x:-20,z:14},api:{x:20,z:14},lounge:{x:-23,z:20},kitchen:{x:22,z:20},entrance:{x:0,z:24}
  };
  function roomFromPosition(x,z){
    let best='corridor',dist=Infinity;
    for(const [id,p] of Object.entries(roomCenters)){const d=Math.hypot(x-p.x,z-p.z);if(d<dist){dist=d;best=id;}}
    return dist<10.5?best:'corridor';
  }

  // Navigation grid is used by autonomous employees so they move around furniture instead of clipping through it.
  const GRID=1.5, GRID_W=44, GRID_H=40, GRID_X=-32, GRID_Z=-29;
  function pointBlocked(x,z,r=.42){
    if(x < -30.7 || x > 30.7 || z < -26.7 || z > 27.0) return true;
    return obstacleBoxes.some(b=>x+r>b.minX&&x-r<b.maxX&&z+r>b.minZ&&z-r<b.maxZ);
  }
  function gridCell(x,z){return {x:clamp(Math.round((x-GRID_X)/GRID),0,GRID_W-1),z:clamp(Math.round((z-GRID_Z)/GRID),0,GRID_H-1)};}
  function gridWorld(c){return {x:GRID_X+c.x*GRID,z:GRID_Z+c.z*GRID};}
  function pathfind(from,to){
    const start=gridCell(from.x,from.z),goal=gridCell(to.x,to.z);
    const key=(c)=>`${c.x},${c.z}`;
    const open=[start],came=new Map(),g=new Map([[key(start),0]]),f=new Map([[key(start),Math.abs(goal.x-start.x)+Math.abs(goal.z-start.z)]]),closed=new Set();
    let iterations=0;
    while(open.length&&iterations++<2600){
      open.sort((a,b)=>(f.get(key(a))??Infinity)-(f.get(key(b))??Infinity));
      const current=open.shift(),ck=key(current);if(current.x===goal.x&&current.z===goal.z){
        const path=[];let k=ck;while(came.has(k)){const [x,z]=k.split(',').map(Number);path.unshift(gridWorld({x,z}));k=came.get(k);}return path;
      }
      closed.add(ck);
      for(const d of [[1,0],[-1,0],[0,1],[0,-1]]){
        const next={x:current.x+d[0],z:current.z+d[1]},nk=key(next);if(next.x<0||next.x>=GRID_W||next.z<0||next.z>=GRID_H||closed.has(nk))continue;
        const pos=gridWorld(next);if(pointBlocked(pos.x,pos.z,.38)&&!(next.x===goal.x&&next.z===goal.z))continue;
        const tentative=(g.get(ck)??Infinity)+1;if(tentative<(g.get(nk)??Infinity)){came.set(nk,ck);g.set(nk,tentative);f.set(nk,tentative+Math.abs(goal.x-next.x)+Math.abs(goal.z-next.z));if(!open.some(c=>key(c)===nk))open.push(next);}
      }
    }
    return [{x:to.x,z:to.z}];
  }
  function setNpcTarget(npc, target, state='walking'){
    npc.target={x:target.x,z:target.z};npc.path=pathfind({x:npc.root.position.x,z:npc.root.position.z},target);npc.pathIndex=0;npc.state=state;
  }
  const routines = {
    lead:[{x:-15,z:-15,label:'Meninjau papan tim'},{x:-18,z:-9,label:'Jeda sejenak'}],
    coo:[{x:-4,z:-12,label:'Memeriksa agenda'},{x:-2,z:-7,label:'Menuju ruang koordinasi'}],
    architect:[{x:24,z:-18,label:'Membaca referensi'},{x:14,z:-11,label:'Jeda sejenak'}],
    frontend:[{x:-25,z:2,label:'Merapikan workstation'},{x:-16,z:5,label:'Jeda sejenak'}],
    qa:[{x:4,z:2,label:'Meninjau checklist'},{x:0,z:5,label:'Istirahat singkat'}],
    backend:[{x:25,z:2,label:'Menuju printer'},{x:17,z:5,label:'Jeda sejenak'}],
    api:[{x:24,z:18,label:'Mengambil minuman'},{x:15,z:11,label:'Kembali ke studio'}]
  };

  const interactables = [
    ...Object.entries(desks).map(([id,d])=>({id:'computer',label:'Workstation',x:d.seat.x,z:d.seat.z+0.1,room:stationByEmployee[id].room})),
    {id:'meeting',label:'Meja meeting',x:-20,z:17.5,room:'meeting'},
    {id:'coffee',label:'Coffee station',x:19,z:20.4,room:'kitchen'},
    {id:'lounge',label:'Lounge',x:-23,z:18.1,room:'lounge'},
    {id:'archive',label:'Rak arsip',x:-26.4,z:-22,room:'corridor'},
    {id:'reception',label:'Resepsionis',x:0,z:15.5,room:'entrance'}
  ];
  let nearbyTarget=null;
  let toastTimer=0, saveTimer=0, lastSaveAt=0, lastSnapshotAt=0, officeSnapshot=null;
  let activeInteractions=[];

  function showToast(message){const node=$('#sim3dToast');if(!node)return;node.textContent=message;node.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove('visible'),2800);}
  function showActionPanel(title,description,actions=[]){
    const panel=$('#sim3dActionCard');if(!panel)return;
    $('#sim3dActionTitle').textContent=title;$('#sim3dActionDescription').textContent=description;
    const host=$('#sim3dActionButtons');host.replaceChildren();
    actions.forEach(({label,view})=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.addEventListener('click',()=>{panel.hidden=true;window.goto?.(view)});host.appendChild(button);});
    panel.hidden=false;
  }
  function normalizedPosition(){return {x:clamp((player.root.position.x+32)/64*100,0,100),y:clamp((player.root.position.z+28)/56*100,0,100)};}
  async function persistPlayer(interaction=null){
    const pos=normalizedPosition();const room=roomFromPosition(player.root.position.x,player.root.position.z);
    try{
      const payload=interaction?{interaction,x:pos.x,y:pos.y,room_id:room}:{x:pos.x,y:pos.y,room_id:room,activity:keys.size?'walking':'idle'};
      const response=await fetch('/api/office/player',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'Posisi gagal disimpan');
      return data.player;
    }catch(error){showToast(`Sinkronisasi kantor gagal: ${error.message}`);return null;}
  }
  async function loadPlayer(){
    try{
      const response=await fetch('/api/office/player',{cache:'no-store'});if(!response.ok)return;
      const data=await response.json();const p=data.player;if(!p)return;
      player.root.position.set(clamp((Number(p.x)/100)*64-32,-28,28),0,clamp((Number(p.y)/100)*56-28,-24,25));
      player.root.rotation.y=0;updateLocationHud();
    }catch(_){/* First-run spawn remains available when the API is offline. */}
  }
  function schedulePlayerSave(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>persistPlayer(),950);}

  function getNearestInteractable(){
    const p=player.root.position;let nearest=null,dist=Infinity;
    for(const item of interactables){const d=Math.hypot(p.x-item.x,p.z-item.z);if(d<dist){dist=d;nearest=item;}}
    const npcNear=[...npcs.values()].map(n=>({id:n.config.id,label:n.config.name,npc:n,d:Math.hypot(p.x-n.root.position.x,p.z-n.root.position.z)})).filter(n=>n.d<2.2).sort((a,b)=>a.d-b.d)[0];
    if(npcNear&&npcNear.d<dist&&npcNear.d<2.2)return {id:'employee',label:npcNear.label,employeeId:npcNear.id,distance:npcNear.d};
    return nearest&&dist<2.6?{...nearest,distance:dist}:null;
  }
  function updateLocationHud(){
    const room=roomFromPosition(player.root.position.x,player.root.position.z);
    const labels={manager:'Lead Manager',planning:'Project Management',architect:'Architecture',frontend:'Frontend Studio',qa:'Quality Assurance',backend:'Backend Engineering',meeting:'Meeting Room',api:'API Studio',lounge:'Lounge',kitchen:'Pantry',entrance:'Reception / Lobby',corridor:'Office Corridor'};
    const node=$('#sim3dLocation');if(node)node.textContent=labels[room]||'Bangkah HQ';
  }
  async function interact(){
    const target=getNearestInteractable();
    if(!target){showToast('Tidak ada objek atau karyawan dalam jangkauan. Dekati objek yang ingin digunakan.');return;}
    if(target.id==='employee'){
      if(document.pointerLockElement===canvas)document.exitPointerLock();
      showToast(`Membuka percakapan dengan ${target.label}.`);window.openEmployeeChat?.(target.employeeId);return;
    }
    if(target.id==='reception'){
      receptionist.state='greeting';receptionist.phase=0;receptionist.routineAt=performance.now()+3500;
      receptionist.meshes.arms[1].rotation.z=-.95;showToast('Mira: Selamat datang di Bangkah. Silakan menuju meja resepsionis.');return;
    }
    const p=normalizedPosition();
    try{
      const response=await fetch('/api/office/player',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interaction:target.id,x:p.x,y:p.y,room_id:roomFromPosition(player.root.position.x,player.root.position.z)})});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'Interaksi gagal');
      const info={
        computer:['Workstation','Akses pekerjaan perusahaan yang tersimpan di backend. Buka daftar tugas, proyek, dan dokumen teknis.',[{label:'Buka Pekerjaan',view:'tasks'},{label:'Knowledge Base',view:'knowledge'}]],
        meeting:['Ruang Meeting','Kelola rapat, agenda, pembagian tugas, serta diskusi bersama Lead Manager.',[{label:'Command Center',view:'manager'},{label:'Ruang Chat',view:'chatrooms'}]],
        archive:['Company Archive','Akses riwayat aktivitas dan dokumen yang tersedia pada sistem kantor.',[{label:'Riwayat Aktivitas',view:'activity'},{label:'Knowledge Base',view:'knowledge'}]],
        coffee:['Coffee Station','Kamu mengambil jeda di pantry. Aktivitas interaksi sudah dicatat ke database kantor.',[]],
        lounge:['Lounge','Karakter kamu sedang beristirahat. Status owner disimpan pada database kantor.',[]]
      }[target.id];
      showToast(data.player?.detail||`Berinteraksi dengan ${target.label}.`);
      player.state=target.id==='computer'?'working':target.id==='meeting'?'meeting':target.id==='coffee'?'coffee':target.id==='lounge'?'resting':'idle';
      player.activityUntil=performance.now()+(target.id==='coffee'?6500:target.id==='lounge'?7000:9000);
      if(info){if(document.pointerLockElement===canvas)document.exitPointerLock();showActionPanel(info[0],info[1],info[2]);}
    }catch(error){showToast(error.message);}
  }

  const keys=new Set();
  let yaw=0,pitch=.26,mouseDown=false,lastMouseX=0,lastMouseY=0,pointerLocked=false;
  let verticalVelocity=0,onGround=true,walkCycle=0,moving=false;
  const moveSpeed=5.3, sprintSpeed=8.4;
  const cameraTarget=new THREE.Vector3();
  const cameraDesired=new THREE.Vector3();
  const raycaster=new THREE.Raycaster(), pointer=new THREE.Vector2();
  const groundPlane=new THREE.Plane(new THREE.Vector3(0,1,0),0);

  function movePlayer(dx,dz){
    const radius=.38;
    const nextX=clamp(player.root.position.x+dx,-30.6,30.6);
    if(!pointBlocked(nextX,player.root.position.z,radius))player.root.position.x=nextX;
    const nextZ=clamp(player.root.position.z+dz,-26.7,27.0);
    if(!pointBlocked(player.root.position.x,nextZ,radius))player.root.position.z=nextZ;
  }
  function onKeyDown(event){
    if(!$('#simulator3d')?.classList.contains('show'))return;
    const key=event.key.toLowerCase();
    if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright',' ','e','shift'].includes(key)&&!event.target.closest('input,textarea,button,[contenteditable="true"]')){
      if(key===' ')event.preventDefault();else if(key!=='shift')event.preventDefault();
      if(key==='e'){if(!event.repeat)interact();return;}
      if(key===' '){if(onGround){verticalVelocity=5.2;onGround=false;}return;}
      keys.add(key);
    }
  }
  function onKeyUp(event){keys.delete(event.key.toLowerCase());}
  window.addEventListener('keydown',onKeyDown);
  window.addEventListener('keyup',onKeyUp);
  window.addEventListener('blur',()=>{keys.clear();});
  canvas.addEventListener('click',()=>{
    if(!pointerLocked&&canvas.requestPointerLock){canvas.requestPointerLock();$('#sim3dStartHint')?.classList.add('hidden');}
  });
  $('#sim3dStartHint')?.addEventListener('click',()=>{
    $('#sim3dStartHint')?.classList.add('hidden');
    if(canvas.requestPointerLock)canvas.requestPointerLock();
  });
  document.addEventListener('pointerlockchange',()=>{pointerLocked=document.pointerLockElement===canvas;$('#sim3dPointerState').textContent=pointerLocked?'MOUSE LOCKED':'KLIK LAYAR UNTUK AKTIFKAN KAMERA';});
  document.addEventListener('mousemove',(event)=>{
    if(pointerLocked){yaw-=event.movementX*.0022;pitch=clamp(pitch-event.movementY*.0018,-.16,.82);}
    else if(mouseDown){yaw-=(event.clientX-lastMouseX)*.004;pitch=clamp(pitch-(event.clientY-lastMouseY)*.003,-.16,.82);lastMouseX=event.clientX;lastMouseY=event.clientY;}
  });
  canvas.addEventListener('pointerdown',(event)=>{if(event.pointerType==='touch'){mouseDown=true;lastMouseX=event.clientX;lastMouseY=event.clientY;}});
  window.addEventListener('pointerup',()=>{mouseDown=false;});
  canvas.addEventListener('wheel',(event)=>{event.preventDefault();cameraDistance=clamp(cameraDistance+Math.sign(event.deltaY)*.7,3.5,10.5);},{passive:false});
  let cameraDistance=6.2;

  // Touch joystick for smaller screens.
  const joystick=$('#sim3dJoystick'),joystickKnob=$('#sim3dJoystickKnob');let joyActive=false,joyOrigin={x:0,y:0},joy={x:0,y:0};
  if(joystick){
    joystick.addEventListener('pointerdown',e=>{joyActive=true;joystick.setPointerCapture(e.pointerId);const r=joystick.getBoundingClientRect();joyOrigin={x:r.left+r.width/2,y:r.top+r.height/2};updateJoy(e);});
    joystick.addEventListener('pointermove',e=>{if(joyActive)updateJoy(e);});
    joystick.addEventListener('pointerup',()=>{joyActive=false;joy={x:0,y:0};if(joystickKnob)joystickKnob.style.transform='translate(0,0)';});
    joystick.addEventListener('pointercancel',()=>{joyActive=false;joy={x:0,y:0};if(joystickKnob)joystickKnob.style.transform='translate(0,0)';});
  }
  function updateJoy(e){const dx=e.clientX-joyOrigin.x,dy=e.clientY-joyOrigin.y,len=Math.hypot(dx,dy)||1,scale=Math.min(1,38/len);joy={x:dx/38*scale,y:dy/38*scale};if(joystickKnob)joystickKnob.style.transform=`translate(${joy.x*38}px,${joy.y*38}px)`;}
  $('#sim3dJump')?.addEventListener('click',()=>{if(onGround){verticalVelocity=5.2;onGround=false;}});
  $('#sim3dSprint')?.addEventListener('pointerdown',()=>keys.add('shift'));
  $('#sim3dSprint')?.addEventListener('pointerup',()=>keys.delete('shift'));
  $('#sim3dSprint')?.addEventListener('pointerleave',()=>keys.delete('shift'));

  function syncNpcFromSnapshot(snapshot){
    if(!snapshot?.office)return;
    officeSnapshot=snapshot.office;
    activeInteractions=(snapshot.office.interactions||[]).filter(row=>new Date(row.expires_at).getTime()>Date.now());
    const employeeRows=snapshot.office.employees||[];
    employeeRows.forEach(row=>{
      const npc=npcs.get(row.id);if(!npc)return;
      const oldStatus=npc.record.status,oldRoom=npc.record.room_id;
      npc.record={...npc.record,...row};
      const station=stationByEmployee[row.id];
      const targetRoom=row.room_id||station.room;
      if(targetRoom!==oldRoom&&roomCenters[targetRoom]){
        const center=roomCenters[targetRoom];npc.home.set(center.x,0,center.z);
        if(row.status!=='working')setNpcTarget(npc,{x:center.x,z:center.z+1.8},'walking');
      }
      if(row.status==='working'){
        const desk=desks[row.id];if(desk&&oldStatus!=='working')setNpcTarget(npc,desk.seat,'working');
        npc.state='working';
      }else if(row.status==='talking'||row.status==='listening'){
        npc.target=null;npc.path=[];npc.pathIndex=0;npc.state=row.status;
      }else if(['failed','blocked'].includes(row.status)){
        npc.state=row.status;
      }else if(oldStatus!==row.status&&row.status==='idle'){
        npc.state='idle';npc.routineAt=performance.now()+4500+Math.random()*9000;
      }
    });
    // Speech is shown only for interactions that are still persisted and active in SQLite.
    npcs.forEach(npc=>npc.setSpeech(null));
    for(const row of activeInteractions.slice(0,10)){
      const sender=npcs.get(row.sender_id);if(sender)sender.setSpeech(row.message||'Berkomunikasi');
      if(row.recipient_id){const receiver=npcs.get(row.recipient_id);if(receiver)receiver.state='listening';}
    }
    const working=employeeRows.filter(e=>e.status==='working').length;
    const talking=employeeRows.filter(e=>e.status==='talking').length;
    const idle=employeeRows.length-working-talking-employeeRows.filter(e=>e.status==='listening').length;
    const put=(id,value)=>{const node=$(id);if(node)node.textContent=String(value);};
    put('#sim3dCountWorking',working);put('#sim3dCountTalking',talking);put('#sim3dCountIdle',idle);
    put('#sim3dRosterCount',employeeRows.length+1);
    const latest=snapshot.project?.name||snapshot.projects?.[0]?.name||'Belum ada proyek aktif';
    put('#sim3dProject',latest);
  }
  async function refreshOfficeSnapshot(){
    try{const response=await fetch('/api/status',{cache:'no-store'});if(!response.ok)throw new Error('status unavailable');const data=await response.json();syncNpcFromSnapshot(data);$('#sim3dConnection').textContent='DATABASE CONNECTED';$('#sim3dConnection').classList.add('online');}
    catch(_){$('#sim3dConnection').textContent='LOCAL SIMULATION';$('#sim3dConnection').classList.remove('online');}
  }

  function updateNpc(npc,dt,now){
    npc.phase+=dt;
    const config=npc.config;
    if(npc===receptionist){
      if(now>npc.routineAt&&npc.state==='greeting'){npc.meshes.arms[1].rotation.z=0;npc.state='idle';npc.routineAt=now+9000;}
      if(npc.state==='idle'&&now>npc.routineAt){npc.state='tablet';npc.routineAt=now+5000;}
      if(npc.state==='tablet'&&now>npc.routineAt){npc.state='greeting';npc.routineAt=now+2200;}
    }else if(npc.record?.status==='idle'&&now>npc.routineAt&&!npc.target){
      const options=routines[config.id]||[];
      if(options.length){const item=options[npc.routineIndex++%options.length];setNpcTarget(npc,item,'walking');npc.routineLabel=item.label;npc.routineAt=now+11000+Math.random()*4500;}
    }
    if(npc.target&&npc.path?.length){
      const point=npc.path[npc.pathIndex];
      if(point){const dx=point.x-npc.root.position.x,dz=point.z-npc.root.position.z,len=Math.hypot(dx,dz);
        if(len<.22){npc.pathIndex++;if(npc.pathIndex>=npc.path.length){npc.target=null;npc.path=[];if(npc.record?.status==='working')npc.state='working';else npc.state='idle';npc.routineAt=now+7000+Math.random()*12000;}}
        else{const step=Math.min(len,(npc.walkSpeed*dt));npc.root.position.x+=dx/len*step;npc.root.position.z+=dz/len*step;npc.root.rotation.y=Math.atan2(-dx,-dz);}
      }
    }
    const walking=!!npc.target;
    const activeWork=npc.record?.status==='working';
    const talk=npc.state==='talking';
    npc.body.position.y=Math.sin(npc.phase*2.2)*.025+(activeWork?Math.sin(npc.phase*5)*.012:0);
    npc.meshes.arms.forEach((arm,i)=>{
      if(walking){arm.rotation.x=Math.sin(npc.phase*8+i*Math.PI)*.62;arm.rotation.z=(i===0?-.08:.08);}
      else if(activeWork){arm.rotation.x=-.62+Math.sin(npc.phase*15+i*1.6)*.14;arm.rotation.z=i===0?-.18:.18;}
      else if(talk){arm.rotation.x=-.38+Math.sin(npc.phase*4+i)*.18;arm.rotation.z=i===0?-.44:.44;}
      else if(npc===receptionist&&npc.state==='greeting'){arm.rotation.x=-.5;arm.rotation.z=i===0?-.1:-.88+Math.sin(npc.phase*9)*.28;}
      else{arm.rotation.x=Math.sin(npc.phase*1.1+i)*.035;arm.rotation.z=i===0?-.05:.05;}
    });
    npc.meshes.legs.forEach((leg,i)=>{leg.rotation.x=walking?Math.sin(npc.phase*8+i*Math.PI)*.55:Math.sin(npc.phase)*.018;});
    npc.nameSprite.position.y=2.78+Math.sin(npc.phase*2)*.025;
    let activity='Jeda · menunggu',activityColor='#dce9dd';
    if(npc===receptionist){activity=npc.state==='greeting'?'Menyambut tamu':npc.state==='tablet'?'Memeriksa jadwal':'Front desk';activityColor='#d8e8e8';}
    else if(npc.record?.status==='working'){activity='Bekerja · tugas aktif';activityColor='#f1dfc9';}
    else if(npc.record?.status==='talking'||npc.state==='talking'){activity='Berbicara';activityColor='#e6dff3';}
    else if(npc.record?.status==='listening'||npc.state==='listening'){activity='Mendengarkan';activityColor='#dcebf1';}
    else if(npc.record?.status==='failed'||npc.state==='failed'){activity='Perlu perhatian';activityColor='#f5d9d5';}
    else if(npc.record?.status==='blocked'||npc.state==='blocked'){activity='Terhambat';activityColor='#f5e3c7';}
    else if(npc.record?.status==='completed'){activity='Tugas selesai';activityColor='#d9eadc';}
    else if(walking){activity=npc.routineLabel||'Berjalan';activityColor='#e4e7d8';}
    if(npc.activitySprite.userData.label!==activity){
      const oldTexture=npc.activitySprite.material.map;
      npc.activitySprite.material.map=labelTexture(activity,activityColor);npc.activitySprite.material.needsUpdate=true;
      npc.activitySprite.userData.label=activity;if(oldTexture)oldTexture.dispose();
    }
  }

  function updatePlayer(dt){
    const forward=Number(keys.has('w')||keys.has('arrowup'))-Number(keys.has('s')||keys.has('arrowdown'))-joy.y;
    const sideways=Number(keys.has('d')||keys.has('arrowright'))-Number(keys.has('a')||keys.has('arrowleft'))+joy.x;
    const vecLen=Math.hypot(forward,sideways);
    moving=vecLen>.12;
    if(moving){
      const fX=-Math.sin(yaw),fZ=-Math.cos(yaw),rX=Math.cos(yaw),rZ=-Math.sin(yaw);
      const dx=(fX*forward+rX*sideways)/vecLen,dz=(fZ*forward+rZ*sideways)/vecLen;
      const speed=(keys.has('shift')?sprintSpeed:moveSpeed)*dt;
      movePlayer(dx*speed,dz*speed);
      player.root.rotation.y=Math.atan2(-dx,-dz);
      walkCycle+=dt*(keys.has('shift')?12:8.5);
    }
    verticalVelocity-=13.5*dt;
    player.root.position.y+=verticalVelocity*dt;
    if(player.root.position.y<=0){player.root.position.y=0;verticalVelocity=0;onGround=true;}
    player.meshes.legs.forEach((leg,i)=>{leg.rotation.x=moving?Math.sin(walkCycle+i*Math.PI)*.62:Math.sin(clock.elapsedTime*1.5+i)*.018;});
    player.meshes.arms.forEach((arm,i)=>{arm.rotation.x=moving?Math.sin(walkCycle+i*Math.PI)*-.42:Math.sin(clock.elapsedTime*1.4+i)*.025;});
    player.body.position.y=moving?Math.abs(Math.sin(walkCycle*2))*.055:Math.sin(clock.elapsedTime*2)*.018;
    const now=performance.now();
    if(player.activityUntil&&now>player.activityUntil){player.state='idle';player.activityUntil=0;}
    if(moving){player.state='walking';if(now-lastSaveAt>1800){lastSaveAt=now;schedulePlayerSave();}}
    else if(keys.size===0&&player.state==='walking'){player.state='idle';schedulePlayerSave();}
    const near=getNearestInteractable();nearbyTarget=near;
    const prompt=$('#sim3dPrompt');if(prompt){prompt.hidden=!near;prompt.textContent=near?`E  ${near.id==='employee'?'Bicara dengan':near.id==='reception'?'Sapa':'Interaksi'} ${near.label}`:'';}
    updateLocationHud();
  }

  function updateCamera(dt){
    const p=player.root.position;
    cameraTarget.set(p.x,p.y+1.35,p.z);
    const horiz=Math.cos(pitch)*cameraDistance;
    cameraDesired.set(p.x+Math.sin(yaw)*horiz,p.y+1.8+Math.sin(pitch)*cameraDistance,p.z+Math.cos(yaw)*horiz);
    camera.position.lerp(cameraDesired,1-Math.pow(.0008,dt));
    camera.lookAt(cameraTarget);
  }

  function onResize(){const width=stage.clientWidth,height=stage.clientHeight;if(!width||!height)return;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();}
  new ResizeObserver(onResize).observe(stage);onResize();

  function updateClockHud(){const node=$('#sim3dClock');if(node)node.textContent=new Date().toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit'});}
  function animate(){
    requestAnimationFrame(animate);
    const dt=Math.min(clock.getDelta(),.045),now=performance.now();
    updatePlayer(dt);
    updateCamera(dt);
    npcs.forEach(npc=>updateNpc(npc,dt,now));
    updateNpc(receptionist,dt,now);
    updateClockHud();
    renderer.render(scene,camera);
  }

  $('#sim3dReset')?.addEventListener('click',()=>{player.root.position.set(0,0,25.1);yaw=0;pitch=.26;player.root.rotation.y=0;persistPlayer();showToast('Posisi karakter dikembalikan ke pintu masuk Bangkah HQ.');});
  $('#sim3dCloseAction')?.addEventListener('click',()=>{$('#sim3dActionCard').hidden=true;});
  $('#sim3dExit')?.addEventListener('click',()=>{if(document.pointerLockElement===canvas)document.exitPointerLock();window.goto?.('wholeOffice');});
  $('#sim3dHelpToggle')?.addEventListener('click',()=>$('#sim3dHelpPanel')?.classList.toggle('open'));

  // Restore the owner's saved location, then connect the simulation to the real office state.
  loadPlayer();
  refreshOfficeSnapshot();
  setInterval(refreshOfficeSnapshot,3500);
  animate();
})();
