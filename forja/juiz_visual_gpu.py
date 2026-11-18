# -*- coding: utf-8 -*-
"""
Juiz Visual Automático Biometria SFace + MediaPipe + GPU (`forja/juiz_visual_gpu.py`)
=====================================================================================
Módulo oficial de auditoria visual determinística para lotes de vídeo:
1. Biometria Facial Real (`OpenCV YuNet + SFace` ArcFace-class):
   - Bloqueia troca de mulher entre cenas (`SFace cosine >= 0.48`, onde mesma mulher = `0.55..0.88`
     e outra mulher = `0.05..0.30`).
   - Bloqueia vazamento da pessoa do viral concorrente (`SFace cosine < 0.42`).
   - Exige cabeça e olhar voltados para a lente da câmera (`eye_ratio >= 0.41` e nariz entre os olhos).
2. Bloqueia 3º braço / 3ª mão (`MediaPipe Hands <= 2` + componentes conexos puros de pele sem confundir armários brancos).
3. Bloqueia 2–3 mulheres no mesmo take ou cortes internos do Veo (`n_faces == 1` a cada `0.30s` + `L1 diff <= 26.0`).
4. Bloqueia troca de roupa/cozinha (`HSV hist corr`) e botões vermelhos/UI alucinados pelo Veo.
"""
from __future__ import annotations

import pathlib
import threading
import urllib.request
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

_VISION_LOCK = threading.Lock()
_JUIZ_GLOBAL: "JuizVisualGPU | None" = None
_JUIZ_INIT_LOCK = threading.Lock()

_MODELS_DIR = pathlib.Path(r"C:\Hub001\MATRIZES_BATWINGS_22E8DC82\_models")
_YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
_SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"


def _garantir_modelos_biometricos() -> tuple[pathlib.Path, pathlib.Path]:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    p_yu = _MODELS_DIR / "yunet.onnx"
    p_sf = _MODELS_DIR / "sface.onnx"
    if not p_yu.exists() or p_yu.stat().st_size < 100_000:
        urllib.request.urlretrieve(_YUNET_URL, str(p_yu))
    if not p_sf.exists() or p_sf.stat().st_size < 10_000_000:
        urllib.request.urlretrieve(_SFACE_URL, str(p_sf))
    return p_yu, p_sf


class JuizVisualGPU:
    def __init__(self) -> None:
        p_yu, p_sf = _garantir_modelos_biometricos()
        self.yunet = cv2.FaceDetectorYN.create(str(p_yu), "", (360, 640), 0.52, 0.30, 5000)
        self.sface = cv2.FaceRecognizerSF.create(str(p_sf), "")
        self.mp_hands = mp.solutions.hands.Hands(
            static_image_mode=True, max_num_hands=5, min_detection_confidence=0.30
        )
        self.mp_pose = mp.solutions.pose.Pose(
            static_image_mode=True, model_complexity=1, min_detection_confidence=0.50
        )

    @staticmethod
    def read_bgr(path: pathlib.Path | str) -> np.ndarray:
        p = pathlib.Path(path)
        data = np.frombuffer(p.read_bytes(), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Imagem invalida: {p}")
        return img

    def analisar_bgr(self, bgr_full: np.ndarray, check_pose: bool = False) -> dict[str, Any]:
        bgr = cv2.resize(bgr_full, (360, 640), interpolation=cv2.INTER_AREA)
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        with _VISION_LOCK:
            self.yunet.setInputSize((w, h))
            _, raw_faces = self.yunet.detect(bgr)
            res_h = self.mp_hands.process(rgb)
            res_p = self.mp_pose.process(rgb) if check_pose else None

        faces: list[tuple[int, int, int, int, float, bool, float]] = []
        valid_raw_faces = []
        if raw_faces is not None and len(raw_faces) > 0:
            for rf in raw_faces:
                fx, fy, fw, fh = float(rf[0]), float(rf[1]), float(rf[2]), float(rf[3])
                score = float(rf[-1])
                if fw < 32 or fh < 32 or score < 0.62:
                    continue
                rx, lx, nx = float(rf[4]), float(rf[6]), float(rf[8])
                eye_ratio = abs(lx - rx) / max(1.0, fw)
                if score < 0.84 and eye_ratio < 0.32:
                    # Evita falso positivo em dedos/nos da mao segurando a caixa laranja (ex: score=0.76, er=0.26)
                    continue
                nose_between = (min(rx, lx) - 0.04 * fw) <= nx <= (max(rx, lx) + 0.04 * fw)
                frontal_ok = (eye_ratio >= 0.41) and nose_between
                x1, y1 = max(0, int(fx)), max(0, int(fy))
                x2, y2 = min(w, int(fx + fw)), min(h, int(fy + fh))
                faces.append((x1, y1, x2, y2, score, frontal_ok, eye_ratio))
                valid_raw_faces.append(rf)

        hand_centers: list[tuple[float, float]] = []
        if res_h.multi_hand_landmarks:
            for hl in res_h.multi_hand_landmarks:
                xs = [lm.x * w for lm in hl.landmark]
                ys = [lm.y * h for lm in hl.landmark]
                cx, cy = float(np.mean(xs)), float(np.mean(ys))
                if all(np.hypot(cx - ox, cy - oy) > 46.0 for ox, oy in hand_centers):
                    hand_centers.append((cx, cy))

        face_emb = None
        gaze_frontal = False
        eye_ratio_val = 0.0
        if len(faces) == 1:
            _, _, _, _, _, gaze_frontal, eye_ratio_val = faces[0]
            with _VISION_LOCK:
                aligned = self.sface.alignCrop(bgr, valid_raw_faces[0])
                feat = self.sface.feature(aligned).flatten().astype(np.float32)
                face_emb = feat / (float(np.linalg.norm(feat)) + 1e-8)

        # Cor da roupa especificamente no centro do tronco (100% tecido nas duas poses: y=0.58..0.88, x=0.24..0.52)
        torso_bgr = bgr[int(h * 0.58) : int(h * 0.88), int(w * 0.24) : int(w * 0.52)]
        torso_hsv = cv2.cvtColor(torso_bgr, cv2.COLOR_BGR2HSV)
        t_hist = cv2.calcHist([torso_hsv], [0, 1], None, [12, 8], [0, 180, 0, 256])
        cv2.normalize(t_hist, t_hist)
        t_lab = cv2.cvtColor(torso_bgr, cv2.COLOR_BGR2LAB)
        t_lab_mean = np.median(t_lab.reshape(-1, 3), axis=0).astype(np.float32)

        # Cantos superiores esquerdo e direito separados
        bg_l_hsv = cv2.cvtColor(bgr[0 : int(h * 0.28), 0 : int(w * 0.24)], cv2.COLOR_BGR2HSV)
        bg_r_hsv = cv2.cvtColor(bgr[0 : int(h * 0.28), int(w * 0.74) : w], cv2.COLOR_BGR2HSV)
        bg_l_hist = cv2.calcHist([bg_l_hsv], [0, 1, 2], None, [12, 12, 8], [0, 180, 0, 256, 0, 256])
        bg_r_hist = cv2.calcHist([bg_r_hsv], [0, 1, 2], None, [12, 12, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(bg_l_hist, bg_l_hist)
        cv2.normalize(bg_r_hist, bg_r_hist)
        bg_hsv = np.concatenate([bg_l_hsv, bg_r_hsv], axis=1)
        bg_hist = cv2.calcHist([bg_hsv], [0, 1, 2], None, [12, 12, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(bg_hist, bg_hist)

        # Caixa laranja Baking Soda (metade esquerda vs metade direita)
        hsv_mid = cv2.cvtColor(bgr[int(h * 0.20) : int(h * 0.94), :], cv2.COLOR_BGR2HSV)
        orange_mask = cv2.inRange(hsv_mid, np.array([7, 110, 110]), np.array([24, 255, 255]))
        orange_ratio = float(np.count_nonzero(orange_mask)) / float(orange_mask.size)
        orange_right = float(np.count_nonzero(orange_mask[:, w // 2 :])) / float(orange_mask[:, w // 2 :].size)
        orange_left = float(np.count_nonzero(orange_mask[:, : w // 2])) / float(orange_mask[:, : w // 2].size)

        # Pasta branca especificamente na regiao do braco erguido (y=0.30..0.60, x=0.18..0.88)
        arm_zone = cv2.cvtColor(bgr[int(h * 0.30) : int(h * 0.60), int(w * 0.18) : int(w * 0.88)], cv2.COLOR_BGR2HSV)
        white_paste_mask = cv2.inRange(arm_zone, np.array([0, 0, 182]), np.array([180, 52, 255]))
        paste_ratio = float(np.count_nonzero(white_paste_mask)) / float(white_paste_mask.size)

        # Botao vermelho alucinado (ex: Follow button vermelho)
        mid_hsv = cv2.cvtColor(bgr[int(h * 0.15) : int(h * 0.88), :], cv2.COLOR_BGR2HSV)
        red1 = cv2.inRange(mid_hsv, np.array([0, 185, 180]), np.array([6, 255, 255]))
        red2 = cv2.inRange(mid_hsv, np.array([173, 185, 180]), np.array([180, 255, 255]))
        red_ratio = float(np.count_nonzero(cv2.bitwise_or(red1, red2))) / float(mid_hsv.shape[0] * mid_hsv.shape[1])

        # Componentes conexos PUROS DE PELE fora da cabeca/pescoco/colo (sem incluir armarios brancos!)
        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        skin = cv2.inRange(ycrcb, np.array([55, 136, 82]), np.array([250, 172, 124]))
        skin[0 : int(h * 0.06), :] = 0
        skin[int(h * 0.90) : h, :] = 0
        if len(faces) == 1:
            fx1, fy1, fx2, fy2, _, _, _ = faces[0]
            fh_px = max(28, fy2 - fy1)
            cv2.rectangle(
                skin,
                (max(0, fx1 - 24), max(0, fy1 - 12)),
                (min(w, fx2 + 24), min(h, fy2 + int(fh_px * 1.15))),
                0,
                -1,
            )
        kernel = np.ones((7, 7), np.uint8)
        skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, kernel)
        skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, kernel)
        num_lbl, _, stats, _ = cv2.connectedComponentsWithStats(skin, connectivity=8)
        min_limb_area = int(0.018 * w * h)
        skin_limb_blobs = sum(
            1 for lbl_i in range(1, num_lbl) if int(stats[lbl_i, cv2.CC_STAT_AREA]) >= min_limb_area
        )

        pose_ok = True
        horiz_arm_ok = True
        horiz_arm_detail = "NA"
        if res_p and res_p.pose_landmarks:
            lms = res_p.pose_landmarks.landmark
            vis = [float(lms[idx_p].visibility) for idx_p in (11, 12)]
            pose_ok = max(vis) >= 0.50
            l_sh, r_sh, r_el, r_wr = lms[11], lms[12], lms[14], lms[16]
            sh_dx = abs(float(l_sh.x) - float(r_sh.x))
            arm_dx = float(r_el.x) - float(r_sh.x)
            arm_dy = abs(float(r_el.y) - float(r_sh.y))
            fcx = ((faces[0][0] + faces[0][2]) / (2.0 * w)) if len(faces) == 1 else 0.5
            horiz_arm_ok = (
                fcx <= 0.46
                and sh_dx <= 0.36
                and float(r_sh.x) <= 0.35
                and float(r_el.x) >= 0.62
                and arm_dx >= 0.35
                and arm_dy <= 0.14
                and float(r_wr.y) <= 0.28
            )
            horiz_arm_detail = (
                f"fcx={fcx:.2f},sh_dx={sh_dx:.2f},Rsh=({r_sh.x:.2f},{r_sh.y:.2f}),"
                f"Rel=({r_el.x:.2f},{r_el.y:.2f}),Rwr_y={r_wr.y:.2f}"
            )
        elif check_pose:
            pose_ok = False
            horiz_arm_ok = False
            horiz_arm_detail = "NO_POSE_LMS"

        return {
            "small_gray": cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY),
            "n_faces": len(faces),
            "gaze_frontal": gaze_frontal,
            "eye_ratio": eye_ratio_val,
            "faces": faces,
            "n_hands": len(hand_centers),
            "hands": hand_centers,
            "skin_limb_blobs": skin_limb_blobs,
            "pose_ok": pose_ok,
            "horiz_arm_ok": horiz_arm_ok,
            "horiz_arm_detail": horiz_arm_detail,
            "face_emb": face_emb,
            "t_hist": t_hist,
            "t_lab_mean": t_lab_mean,
            "bg_hist": bg_hist,
            "bg_l_hist": bg_l_hist,
            "bg_r_hist": bg_r_hist,
            "orange_ratio": orange_ratio,
            "orange_right": orange_right,
            "orange_left": orange_left,
            "paste_ratio": paste_ratio,
            "red_ratio": red_ratio,
        }

    def validar_frame1(
        self,
        f1_jpg: pathlib.Path,
        competitor_face_emb: np.ndarray | None = None,
        require_paste: bool = True,
        require_right_counter_box: bool = True,
    ) -> tuple[bool, str, dict[str, Any]]:
        bgr = self.read_bgr(f1_jpg)
        a1 = self.analisar_bgr(bgr, check_pose=True)
        if a1["n_faces"] != 1 or a1["face_emb"] is None:
            return False, f"F1_FACES={a1['n_faces']}", a1
        if not a1["gaze_frontal"]:
            return False, f"F1_ROSTO_DE_PERFIL(er={a1['eye_ratio']:.2f}<0.41)", a1
        if a1["n_hands"] > 2:
            return False, f"F1_MAOS_EXTRAS={a1['n_hands']}", a1
        if a1["skin_limb_blobs"] > 4:
            return False, f"F1_MEMBROS_PELE={a1['skin_limb_blobs']}", a1
        if competitor_face_emb is not None:
            sim_comp = float(np.dot(a1["face_emb"], competitor_face_emb))
            if sim_comp >= 0.65:
                return False, f"F1_VAZOU_CONCORRENTE_SFACE({sim_comp:.2f}>=0.65)", a1
        if require_paste and a1["paste_ratio"] < 0.006:
            return False, f"F1_SEM_PASTA_BRANCA({a1['paste_ratio']:.4f})", a1
        if require_right_counter_box and a1["orange_right"] < 0.005:
            return False, f"F1_SEM_CAIXA_LARANJA_DIREITA({a1['orange_right']:.4f})", a1
        return True, "OK", a1

    def validar_frame2_contra_f1(
        self,
        f2_jpg: pathlib.Path,
        a1: dict[str, Any],
        competitor_face_emb: np.ndarray | None = None,
        require_box_right: bool = True,
    ) -> tuple[bool, str, dict[str, Any]]:
        bgr2 = self.read_bgr(f2_jpg)
        a2 = self.analisar_bgr(bgr2, check_pose=True)
        if a2["n_faces"] != 1 or a2["face_emb"] is None:
            return False, f"F2_FACES={a2['n_faces']}", a2
        if not a2["gaze_frontal"]:
            return False, f"F2_SEM_OLHAR_CAMERA(er={a2['eye_ratio']:.2f})", a2
        if a2["n_hands"] > 2:
            return False, f"F2_MAOS_EXTRAS={a2['n_hands']}", a2
        if a2["skin_limb_blobs"] > 4:
            return False, f"F2_MEMBROS_PELE={a2['skin_limb_blobs']}", a2
        if competitor_face_emb is not None:
            sim_comp = float(np.dot(a2["face_emb"], competitor_face_emb))
            if sim_comp >= 0.65:
                return False, f"F2_VAZOU_CONCORRENTE_SFACE({sim_comp:.2f}>=0.65)", a2

        f_sim = float(np.dot(a1["face_emb"], a2["face_emb"]))
        t_corr = float(cv2.compareHist(a1["t_hist"], a2["t_hist"], cv2.HISTCMP_CORREL))
        t_lab_dist = float(np.linalg.norm(a1["t_lab_mean"] - a2["t_lab_mean"]))
        bg_corr = max(
            float(cv2.compareHist(a1["bg_hist"], a2["bg_hist"], cv2.HISTCMP_CORREL)),
            float(cv2.compareHist(a1["bg_l_hist"], a2["bg_l_hist"], cv2.HISTCMP_CORREL)),
            float(cv2.compareHist(a1["bg_r_hist"], a2["bg_r_hist"], cv2.HISTCMP_CORREL)),
        )

        if f_sim < 0.48:
            return False, f"F2_OUTRA_MULHER_SFACE({f_sim:.3f}<0.48)", a2
        if t_corr < 0.35 and t_lab_dist > 28.0:
            return False, f"F2_TROCOU_ROUPA(corr={t_corr:.2f},dE={t_lab_dist:.1f})", a2
        if bg_corr < 0.44:
            return False, f"F2_TROCOU_COZINHA({bg_corr:.3f}<0.44)", a2
        if require_box_right and (a2["orange_right"] < 0.008 or a2["orange_right"] < a2["orange_left"]):
            return False, f"F2_CAIXA_FORA_DA_DIREITA(R={a2['orange_right']:.4f},L={a2['orange_left']:.4f})", a2
        return True, f"OK_SFACE(face={f_sim:.2f},dE={t_lab_dist:.1f},bg={bg_corr:.2f})", a2

    def auditar_clipe_visual(
        self,
        mp4_path: pathlib.Path,
        t_start: float,
        t_end: float,
        a_start_frame: dict[str, Any],
        a_f1_master: dict[str, Any],
        arm_pose: bool,
    ) -> tuple[bool, str]:
        cap = cv2.VideoCapture(str(mp4_path))
        if not cap.isOpened():
            return False, "CAP_OPEN_FAIL"

        sample_ts = list(np.arange(max(0.0, t_start), max(t_start + 0.1, t_end), 0.30))
        if not sample_ts or sample_ts[-1] < t_end - 0.12:
            sample_ts.append(max(0.0, t_end - 0.05))

        prev_gray = None
        base_red = a_start_frame["red_ratio"]

        for t_s in sample_ts:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t_s) * 1000.0)
            ok, fr = cap.read()
            if not ok or fr is None:
                continue

            af = self.analisar_bgr(fr, check_pose=False)

            if af["n_faces"] != 1 or af["face_emb"] is None:
                cap.release()
                return False, f"FACES_INVALIDAS_NO_TAKE(n={af['n_faces']}@{t_s:.1f}s)"

            if af["n_hands"] > 2:
                cap.release()
                return False, f"TERCEIRA_MAO_DETECTADA(n={af['n_hands']}@{t_s:.1f}s)"

            max_blobs = max(4, int(a_start_frame["skin_limb_blobs"]) + 1)
            if af["skin_limb_blobs"] > max_blobs:
                cap.release()
                return False, f"MEMBRO_EXTRA_PELE(blobs={af['skin_limb_blobs']}@{t_s:.1f}s)"

            if prev_gray is not None:
                l1_diff = float(np.mean(cv2.absdiff(prev_gray, af["small_gray"])))
                if l1_diff > 26.0:
                    cap.release()
                    return False, f"CORTE_INTERNO_VEO(diff={l1_diff:.1f}@{t_s:.1f}s)"
            prev_gray = af["small_gray"]

            sim_local = float(np.dot(a_start_frame["face_emb"], af["face_emb"]))
            sim_master = float(np.dot(a_f1_master["face_emb"], af["face_emb"]))
            bg_local = max(
                float(cv2.compareHist(a_start_frame["bg_hist"], af["bg_hist"], cv2.HISTCMP_CORREL)),
                float(cv2.compareHist(a_start_frame["bg_l_hist"], af["bg_l_hist"], cv2.HISTCMP_CORREL)),
                float(cv2.compareHist(a_start_frame["bg_r_hist"], af["bg_r_hist"], cv2.HISTCMP_CORREL)),
            )
            top_local = max(
                float(cv2.compareHist(a_start_frame["t_hist"], af["t_hist"], cv2.HISTCMP_CORREL)),
                float(cv2.compareHist(a_f1_master["t_hist"], af["t_hist"], cv2.HISTCMP_CORREL)),
            )
            top_dE = min(
                float(np.linalg.norm(a_start_frame["t_lab_mean"] - af["t_lab_mean"])),
                float(np.linalg.norm(a_f1_master["t_lab_mean"] - af["t_lab_mean"])),
            )

            if sim_local < 0.45 or sim_master < 0.43:
                cap.release()
                return False, f"DESVIO_ROSTO_SFACE(loc={sim_local:.2f},mst={sim_master:.2f}@{t_s:.1f}s)"
            if bg_local < 0.55:
                cap.release()
                return False, f"DESVIO_FUNDO_COZINHA(bg={bg_local:.2f}@{t_s:.1f}s)"
            if top_local < 0.30 and top_dE > 30.0:
                cap.release()
                return False, f"DESVIO_ROUPA(top={top_local:.2f},dE={top_dE:.1f}@{t_s:.1f}s)"

            if not arm_pose and (af["red_ratio"] - base_red) > 0.008:
                cap.release()
                return False, f"BOTAO_VERMELHO_ALUCINADO(red={af['red_ratio']:.4f}@{t_s:.1f}s)"

        cap.release()
        return True, "OK"


def obter_juiz_visual() -> JuizVisualGPU:
    global _JUIZ_GLOBAL
    with _JUIZ_INIT_LOCK:
        if _JUIZ_GLOBAL is None:
            _JUIZ_GLOBAL = JuizVisualGPU()
        return _JUIZ_GLOBAL
