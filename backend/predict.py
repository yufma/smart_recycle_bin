"""beta-2 분류 실행 스크립트 (4클래스: CAN, PET, GLASS, OTHER).

필요한 것: Python 3.9 이상, torch, torchvision, pillow, numpy (GPU 없어도 됨).
    pip install torch torchvision pillow numpy

사용 예:
    python predict.py --model beta-2b.pt 사진.jpg
    python predict.py --model beta-2b.pt 사진폴더 --csv 결과.csv
    python predict.py --model beta-2a.pt 원본.jpg --box 812,430,1260,1105

입력 사진은 기기와 같은 구도(물체 1개가 가운데, 물체 상자가 화면의 35-45 %)여야 학습 때와 같은 조건이 됩니다.
--box x0,y0,x1,y1 (원본 픽셀 좌표의 물체 상자)를 주면 학습 평가 때와 똑같은 40 % 구도(eval40)로 잘라서 분류합니다.
전처리: EXIF 회전 반영, RGB, 비율 유지 224 리사이즈(bilinear) + 회색(114) 여백, ImageNet 평균/표준편차 정규화.
GLASS 임계값: 1등이 GLASS인데 GLASS 확률이 임계값보다 낮으면 OTHER로 보냅니다 (beta-2a .65, beta-2b .70)."""
import argparse, csv, io, math, sys
from pathlib import Path
import numpy as np, torch
from PIL import Image, ImageOps
from torchvision import transforms
from torchvision.models import mobilenet_v2

CLASSES = ['CAN', 'PET', 'GLASS', 'OTHER']
GLASS_T = {'beta-2a': .65, 'beta-2b': .70}
TF = transforms.Compose([transforms.ToTensor(), transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

def letterbox(im, size=224):
    w, h = im.size; r = min(size / w, size / h)
    im = im.resize((max(1, round(w * r)), max(1, round(h * r))), Image.Resampling.BILINEAR)
    c = Image.new('RGB', (size, size), (114, 114, 114)); c.paste(im, ((size - im.width) // 2, (size - im.height) // 2)); return c

def eval40(im, box):
    """학습 평가와 같은 40 % 구도: 상자 중심의 정사각 창(한 변 = max(sqrt(상자넓이/.40), 1.02 x 상자 긴 변)), 창이 사진 밖으로 나가면 안쪽으로 밀고,
    사진보다 큰 창은 테두리 중앙값 색으로 채운 뒤 320 px로 줄이고 JPEG 95로 저장했다가 다시 읽습니다(학습 캐시와 동일)."""
    W, H = im.size; x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]); bw, bh = x1 - x0, y1 - y0
    if bw < 4 or bh < 4: raise ValueError('상자가 너무 작습니다')
    a = np.asarray(im); fill = tuple(int(v) for v in np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0))
    s = max(math.sqrt(bw * bh / .40), 1.02 * max(bw, bh)); wx = (x0 + x1) / 2 - s / 2; wy = (y0 + y1) / 2 - s / 2
    if s <= W: wx = min(max(wx, 0), W - s)
    if s <= H: wy = min(max(wy, 0), H - s)
    c = Image.new('RGB', (int(round(s)), int(round(s))), fill)
    ix0, iy0 = max(0, int(round(wx))), max(0, int(round(wy))); ix1, iy1 = min(W, int(round(wx + s))), min(H, int(round(wy + s)))
    c.paste(im.crop((ix0, iy0, ix1, iy1)), (ix0 - int(round(wx)), iy0 - int(round(wy))))
    b = io.BytesIO(); c.resize((320, 320), Image.Resampling.LANCZOS).save(b, 'JPEG', quality=95); b.seek(0)
    return Image.open(b).convert('RGB')

def load(path):
    ck = torch.load(path, map_location='cpu', weights_only=True)
    m = mobilenet_v2(weights=None, num_classes=4); m.load_state_dict(ck['state_dict'], strict=True); return m.eval()

def main():
    a = argparse.ArgumentParser(description='beta-2 4클래스 분류'); a.add_argument('--model', required=True, help='beta-2a.pt 또는 beta-2b.pt')
    a.add_argument('images', nargs='+', help='사진 파일 또는 폴더'); a.add_argument('--box', help='x0,y0,x1,y1 (사진 1장일 때만)')
    a.add_argument('--threshold', type=float, help='GLASS 임계값 (기본: beta-2a .65, beta-2b .70)'); a.add_argument('--csv', help='결과를 CSV로 저장')
    a.add_argument('--cpu', action='store_true', help='GPU가 있어도 CPU로 실행'); a = a.parse_args()
    t = a.threshold if a.threshold is not None else GLASS_T.get(Path(a.model).stem)
    if t is None: sys.exit('모델 이름이 beta-2a / beta-2b가 아니면 --threshold를 지정해 주세요')
    files = []
    for p in map(Path, a.images): files += sorted(f for f in p.rglob('*') if f.suffix.lower() in EXT) if p.is_dir() else [p]
    box = [float(v) for v in a.box.split(',')] if a.box else None
    if box and len(files) != 1: sys.exit('--box는 사진 1장일 때만 쓸 수 있습니다')
    dev = torch.device('cuda' if torch.cuda.is_available() and not a.cpu else 'cpu'); m = load(a.model).to(dev); out = []
    with torch.inference_mode():
        for f in files:
            with Image.open(f) as im: im = ImageOps.exif_transpose(im).convert('RGB')
            if box: im = eval40(im, box)
            p = m(TF(letterbox(im)).unsqueeze(0).to(dev)).float().softmax(1)[0].cpu().numpy(); k = int(p.argmax())
            if k == 2 and p[2] < t: k = 3
            out.append([str(f), CLASSES[k]] + [f'{v:.4f}' for v in p]); print(f'{CLASSES[k]:5s}  ' + '  '.join(f'{c} {v:.3f}' for c, v in zip(CLASSES, p)) + f'  {f}')
    if a.csv:
        with open(a.csv, 'w', newline='', encoding='utf-8-sig') as fh: w = csv.writer(fh); w.writerow(['file', 'class'] + [f'p_{c}' for c in CLASSES]); w.writerows(out)

if __name__ == '__main__': main()
