# Grid Floor Editor

Local-first editor สำหรับแก้ Room Grid และ Portal ของ `floor02` / F2+ แบบ cell-level

## เปิดใช้งาน

เปิด `index.html` ใน browser ได้โดยตรง ตัว editor จะโหลดข้อมูล F2 ที่ bundle ไว้ให้ก่อน

ถ้าต้องการอ่านข้อมูลล่าสุดจาก working tree ให้เปิดผ่าน static server ที่ repository root
แล้วกด **โหลดจากโปรเจกต์** หรือเลือกไฟล์ด้วยปุ่มนำเข้า:

- `WORLD/COMPILED_NAV/floor02_room_cells.json`
- `WORLD/REGISTRY/portals.json`
- occupancy JSON ที่มี `occupied_cells_uv` (ถ้ามี)

## การแก้ไข

1. เลือก layer: `Room Grid`, `Portal Inside` หรือ `Portal Outside`
2. เลือก cell ทีละช่องหรือใช้เครื่องมือคลุมเป็นกรอบ
3. กด **เปิด** เพื่อเพิ่ม cell หรือ **ปิด** เพื่อลบ cell
4. ตรวจ validation และ diff ทางขวา
5. Export เป็น `*_grid_patch.json` ก่อนนำไป apply กับ canonical files

`floor02` เป็น canonical family ดังนั้นการแก้ไขมีผลกับ F2+ จำนวน 23 floors

## ขอบเขตของ MVP

Editor นี้ยังไม่เขียนทับ `room_domains.json`, `portals.json` หรือ compiled masks โดยตรง
เพื่อป้องกันการแก้ canonical data โดยไม่ผ่าน review; output ที่ปลอดภัยสำหรับรอบนี้คือ
patch หรือ snapshot JSON ที่ตรวจสอบและนำไป apply ในขั้นตอนถัดไปได้
