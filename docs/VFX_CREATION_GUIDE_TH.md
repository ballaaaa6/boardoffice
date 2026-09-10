# คู่มือสร้าง VFX แบบพิกเซลสำหรับ GDS

คู่มือนี้เป็น workflow ที่ใช้สร้าง VFX แบบ native pixel ในโปรเจกต์นี้จริง
โดยอ้างอิงจากการทำ `core_charge_blue_v4` และการทดลองประกอบลงฉาก `floor00`.
เป้าหมายคือให้ทำเอฟเฟกต์ใหม่ได้ซ้ำ โดยไม่ทำให้สเกลพิกเซล เพดานระบบ หรือ
ลำดับการวาดของฉากเสีย

## 1. สิ่งที่ระบบใช้อยู่

VFX ไม่ได้ถูกสร้างขึ้นแบบ procedural ทุกเฟรมตอน runtime แต่เป็นภาพ RGBA
หลายเฟรมที่ registry ชี้ไปยัง asset แล้ว renderer เลือกเฟรมตามเวลา

แหล่งอ้างอิงหลัก:

- `CHARACTER/EFFECTS/gds_effects_v1.json` — id, ชื่อ, canvas, frame order,
  ความเร็ว, ตำแหน่ง anchor และ layer
- `CHARACTER/ASSETS/effects/<effect_id>/` — PNG native ของแต่ละ source frame
- `CHARACTER/RUNTIME/effect_renderer.py` — โหลดเฟรม, เล่น loop และ mirror direction
- `CHARACTER/RUNTIME/presentation_renderer.py` — วาง VFX หลังตัวละคร
- `RUNTIME/work_seat_core.py` — ประกอบ VFX เข้ากับ work scene
- `WEB/runtime_canvas_renderer.js` — วาด VFX ใน browser renderer

VFX ปัจจุบันใช้ canvas native `33x65` พิกเซล และวางด้วยกฎ
`layer_mode: behind_character`. ตำแหน่งหลักยึดจาก `character_work_origin`
ไม่ควรเดาตำแหน่งใหม่จากภาพขยาย

## 2. ขั้นตอนทำงานมาตรฐาน

### ขั้นที่ A — สำรวจของเดิมก่อนวาด

1. เปิด registry แล้วนับ effect ที่มีอยู่ รวมถึง `effect_order`.
2. เปิดภาพ native ของ `fire_original` ทั้ง 4 source frame ก่อน เพราะเป็น
   reference หลักด้านมวลไฟและการเปลี่ยนรูปทรง.
3. ดูเอฟเฟกต์อื่นให้ครบ เพื่อสังเกต grammar ที่ระบบมีอยู่ เช่น
   ลมเป็นเส้นไหล, thunder เป็นก้อนมืดกับรอยแตก, bloom เป็นมวลสว่าง.
4. ดูตัวอย่างกับฉากจริง ไม่ตัดสินจาก sheet อย่างเดียว. ไฟล์ตัวอย่างที่ทำไว้คือ
   `LOCAL_REVIEW/core_charge_blue_v4/floor00_full_scene_gif/`.

สิ่งที่ต้องจดก่อนเริ่ม:

| รายการ | ค่าที่ต้องล็อก |
|---|---|
| Canvas | `33x65` native pixels |
| จำนวนเฟรม | ปกติ 10 เฟรมสำหรับเอฟเฟกต์ใหม่ |
| เวลา | `240ms/frame`, loop `2400ms` |
| Alpha | มีแค่ `0` และ `255` |
| Anchor | `character_work_origin` |
| Layer | อยู่หลังตัวละคร |
| Direction | วาด source ตามทิศหลัก แล้ว mirror ทิศ derived |

### ขั้นที่ B — ออกแบบการเคลื่อนไหวก่อนลงสี

ออร่าที่อ่านว่าสมจริงควรมีอย่างน้อย 3 ชั้น:

1. **Core / envelope** — มวลสว่างด้านใน ทำหน้าที่ให้เห็นว่าพลังหุ้มตัว
2. **Primary silhouette** — ขอบหลักที่บอกบุคลิกของพลัง เช่น เปลวโค้งหรือ
   คลื่นที่พุ่งขึ้น
3. **Secondary currents** — เส้นหรือเปลวรองที่เคลื่อนเหลื่อมกัน เติมมิติและ
   ทำให้แต่ละเฟรมคาดเดาไม่ได้เกินไป

กฎการเคลื่อนไหวที่ใช้ได้กับออร่า charge:

- อย่าขยาย/หดทั้งภาพพร้อมกัน ให้ยอดบน ด้านข้าง และแกนกลางเคลื่อนคนละ phase
- รักษามวลหลักไว้บางส่วน เพื่อให้ตัวละครไม่หายไปใน noise
- ให้ปลายเปลวมีความสูงและความโค้งไม่เท่ากัน
- ใส่ประกายหรือรอยพลังเฉพาะบางเฟรม ไม่ใช่ทุกเฟรม
- เฟรมสุดท้ายต้องต่อกับเฟรมแรกได้ โดยตำแหน่งมวลไม่กระโดด
- อย่าทำขอบเป็นสามเหลี่ยมคมซ้ำ ๆ เพราะจะดูเป็นรูปทรงที่คาดเดาได้

สำหรับสไตล์ชาร์จพลังน้ำเงินที่ทำสำเร็จ:

- ด้านในเป็น cyan/white ที่สว่างและกว้าง
- รอบนอกเป็น cobalt/blue หลายระดับ ไม่ใช่สีน้ำเงินเดียว
- มีเปลวโค้งหลายยอดที่สูงไม่เท่ากัน
- มี side current และ ground-pressure arc แบบแยกส่วน
- มี white glint สั้น ๆ ในบางเฟรม

### ขั้นที่ C — วาดบนกริด native

วาดที่ `33x65` เท่านั้น. ภาพ 4x หรือ 6x เป็น preview สำหรับดูเท่านั้น

กติกาพิกเซล:

- เว้น transparent moat รอบขอบอย่างน้อย 1 พิกเซลถ้า silhouette อนุญาต
- อย่าวาดด้วยเส้น vector ที่ถูก rasterize ภายหลัง เพราะจะได้ขอบไม่สม่ำเสมอ
- ใช้ palette ที่ไล่ค่าอย่างตั้งใจ: deep blue → blue → cyan → pale cyan/white
- เงาใช้สีเข้มของ palette ไม่ใช้ alpha โปร่งครึ่ง เพราะ runtime ตรวจ binary alpha
- ทำแต่ละ frame ให้มีการเปลี่ยนจริง แต่ไม่สุ่ม pixel อิสระจนเกิด noise
- ตั้งชื่อและเก็บ `drawing.js`/`pixels.json` ไว้ด้วย เพื่อ reproduce ได้

โครงสร้าง review ที่แนะนำ:

```text
LOCAL_REVIEW/<effect_name>/
  drawing.js                 # สูตร/พิกัดการวาดที่ reproduce ได้
  pixels.json                # pixel payload ที่เขียนเข้า Aseprite
  core_charge.aseprite       # source ที่แก้ต่อได้
  frame_00.png ... frame_09.png
  sheet_native.png           # sheet native 5x2
  sheet_4x.png               # review เท่านั้น, nearest-neighbor
  charge_native.gif
  charge_6x.gif
  verify_exports.py
  README.md
```

### ขั้นที่ D — เขียนลง Aseprite

ใช้ Aseprite MCP สร้าง sprite ใหม่ที่ `33x65`, `10 frames`, `240ms` แล้ว
เขียน pixels แบบ native ลงทีละ frame. MCP ใช้ index แบบ 1-based:

```text
frameIndex = 1..10
layerIndex = 1
```

ถ้า payload ใหญ่ ให้แบ่งการส่งเป็น chunks ประมาณ 65 pixels ต่อครั้ง เพื่อไม่ให้
คำสั่งบน Windows ยาวเกินไป. ทุกครั้งต้องเขียน pixel โปร่งใสด้วยเมื่อจำเป็น
เพื่อลบของเก่า อย่าพึ่งการระบายพื้นหลังโดยไม่ตรวจ alpha.

หลังวาดเสร็จ export sheet ด้วย Aseprite CLI โดยไม่ใช้ `--scale`:

```powershell
& '.\aseprite\portable-v1.3.7\aseprite.exe' -b `
  'LOCAL_REVIEW\<effect>\core_charge.aseprite' `
  --sheet-columns 5 `
  --sheet 'LOCAL_REVIEW\<effect>\sheet_native.png' `
  --data 'LOCAL_REVIEW\<effect>\frames.json'
```

Aseprite `--scale` อาจ smooth ภาพ. การขยาย review ให้ใช้ Pillow
`Image.Resampling.NEAREST` เท่านั้น.

### ขั้นที่ E — ตรวจ asset ก่อนเอาไปเข้าฉาก

ขั้นต่ำที่ต้องผ่าน:

- ขนาดทุก frame เป็น `33x65`
- มีครบ 10 frames และทุก frame แตกต่างกัน
- alpha มีเฉพาะ `0/255`
- GIF มี 10 frames, `240ms/frame`, loop `2400ms`
- pixel ใน GIF ที่ decode กลับมาตรงกับ PNG native
- transparent moat และไม่มีขอบล้น canvas
- sheet crop แต่ละช่องตรงกับ `pixels.json`
- ตรวจดู native 1x และ enlarged sheet ด้วยสายตา

`verify_exports.py` ของ `core_charge_blue_v4` เป็นแม่แบบตรวจที่ใช้ซ้ำได้.
อย่าถือว่า audit ผ่านแล้วแปลว่างานสวย ต้องมี visual review ด้วย

### ขั้นที่ F — ทดลองกับตัวละครและฉากจริง

ทำ review สองระดับ:

1. **Character-only crop** — ใช้ตัวละครจริง 1 ตัวกับ VFX เพื่อดู anchor, scale,
   การบังตัวละคร และความอ่านง่าย
2. **Full scene** — ใช้ `CentralGameCore.render_floor_with_work_effects`
   ประกอบ floor จริง แล้วใส่ VFX ให้ตัวละครทุกตัวใน floor อย่างน้อยหนึ่ง floor

ตัวอย่างที่ทำสำเร็จ:

```text
LOCAL_REVIEW/core_charge_blue_v4/
  floor00_first_character_gif/
  floor00_full_scene_gif/
```

การ review ฉากต้องตรวจว่า:

- VFX อยู่หลังตัวละคร ไม่บังหน้า/ลำตัวเกินจำเป็น
- anchor ไม่ลอยจากเท้าหรือหัว
- ขนาดยังเข้ากับตัวละครหลายทิศทาง
- foreground ของเก้าอี้/โต๊ะยังอยู่ลำดับเดิม
- ตัวละครทุกตัวในฉากได้ effect โดยไม่ไปทับกันผิดจาก scene compositor
- สีของ VFX ไม่ทำให้พื้นหรือ sprite อ่านยากเกินไป

สำหรับ preview ที่ยังไม่อนุมัติ ให้ inject effect ใน memory แบบที่
`floor00_full_scene_gif/render.py` ทำอยู่. อย่าแก้ registry เพียงเพื่อทำ GIF
ตัวอย่าง.

## 3. การทำ Direction

ระบบรองรับ `NW`, `SE`, `SW`, `NE`. โดยทั่วไปให้สร้าง source เฉพาะทิศหลัก
แล้วให้ registry ระบุ derived direction:

```json
"SW": {
  "source": "derived",
  "derived_from": "SE",
  "transform": "mirror_y"
}
```

ใน runtime ชื่อ `mirror_y` หมายถึงการ mirror ตามแกนที่ระบบกำหนดไว้แล้ว
อย่ากลับไปใช้ `transpose` แบบเดาเองใน production. ตรวจทุกทิศด้วยตัวละครจริง
ก่อน integrate เพราะบางเอฟเฟกต์มี asymmetry ที่ mirror แล้วอ่านผิดได้

## 4. การ integrate เข้า runtime หลัง author approve

ทำเฉพาะเมื่อผู้ใช้อนุมัติภาพและขอ integrate ชัดเจน:

1. คัดลอก PNG source frames เข้า
   `CHARACTER/ASSETS/effects/<effect_id>/`.
2. เพิ่ม asset records และ hash ให้ครบใน asset registry.
3. เพิ่ม effect record ใน `CHARACTER/EFFECTS/gds_effects_v1.json` โดยระบุ
   canvas, animation, frame asset ids และ render placement.
4. ตรวจว่า `effect_order` และ automatic VFX bag จะเปลี่ยนตามเจตนาหรือไม่.
5. ตรวจ manifest/browser bundle ที่สร้างจาก registry.
6. รัน renderer tests, full pytest และ validation ที่เกี่ยวข้อง.
7. ทำ full-scene GIF ใหม่จาก runtime path แล้วให้ author ตรวจอีกครั้ง.

ห้าม integrate เพียงเพราะ PNG/GIF ดูดี. Visual acceptance และ production
integration เป็นคนละ gate.

## 5. สิ่งที่ไม่ควรทำ

- อย่าแก้ canonical `fire_original` เพื่อทดลองสีหรือรูปทรงใหม่
- อย่าเอาไฟล์ GIF หรือ sheet review เข้า runtime registry
- อย่าใช้ภาพขยายเป็น source ในการวาดกลับลง native grid
- อย่าใช้ smooth resize หรือ anti-aliasing
- อย่าใส่ alpha กลาง ๆ เพื่อหลบการวาดขอบ
- อย่าวาดทุกเฟรมให้เหมือนกันแล้วเลื่อนทั้งกลุ่ม
- อย่าแก้ runtime เพื่อชดเชย anchor ที่ผิดใน asset
- อย่า mark milestone ว่าปิดก่อน author visual acceptance

## 6. Checklist สั้นก่อนส่งรีวิว

- [ ] สำรวจ canonical effects และเลือก reference grammar แล้ว
- [ ] ล็อก `33x65`, จำนวนเฟรม และ `240ms`
- [ ] วาด native ด้วย palette และ binary alpha
- [ ] มี core, primary silhouette และ secondary currents
- [ ] ทุก frame เปลี่ยนแบบควบคุมได้และ loop ต่อกัน
- [ ] Aseprite source, pixel payload และ drawing source เก็บครบ
- [ ] QA ผ่านขนาด, alpha, unique frames, GIF timing และ exact pixels
- [ ] ดู native 1x และ nearest-neighbor enlarged sheet
- [ ] ทดลอง character-only crop
- [ ] ทดลอง full-scene compositor อย่างน้อยหนึ่ง floor
- [ ] ยังไม่ integrate จนกว่าจะได้รับ visual approval ชัดเจน
