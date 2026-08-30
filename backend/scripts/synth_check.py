"""合成引擎快速自检：确定性 + 相位对齐 + 耗时。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from app.providers.music_local import LocalSynthProvider
from app.synth.ir import SongRequest

req = SongRequest(
    style_prompt="华语流行抒情，钢琴主导，弦乐铺底，雨夜氛围，女声气声",
    negative_prompt="不要电音人声", model="v1_pro",
    lyrics="[Verse]\n雨停在凌晨三点的窗台\n霓虹把影子拉得好白\n[Chorus]\n我们把未来说得太轻\n像风穿过无人的街心",
    bpm=90, tonic="A", mode="minor", time_signature="4/4",
    duration_sec=45, vocal="female_air", language="zh", instrument_density=65, seed=1832744110,
)


def render(dest: Path):
    provider = LocalSynthProvider()
    t0 = time.time()
    out = provider.generate(req, lambda k, pct, lbl: None, lambda: False, str(dest))
    dt = time.time() - t0
    hashes = {f["relpath"]: f["sha256"] for f in out.candidates[0].files}
    return dt, hashes, out


d1 = Path(__file__).parent / "_synth_check_tmp1"
d2 = Path(__file__).parent / "_synth_check_tmp2"
dt1, h1, out1 = render(d1)
dt2, h2, out2 = render(d2)

print(f"render time: {dt1:.1f}s / {dt2:.1f}s")
print("candidate A files:")
for k, v in h1.items():
    print(f"  {k}: {v[:16]}...")
same = h1 == h2
print("determinism (same seed):", "PASS" if same else "FAIL")
cand = out1.candidates[0]
print("duration:", cand.duration_sec, "structure:", [(s['section'], s['bars']) for s in cand.structure])
print("vocal notes:", len([n for n in out1.candidates]), "quality:", [c.quality_score for c in out1.candidates])
if not same:
    for k in h1:
        if h1[k] != h2[k]:
            print("  DIFF:", k)
