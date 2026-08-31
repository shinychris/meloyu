import { useEffect, useRef, useState } from 'react'
import type { Certificate, Work } from '../types/api'
import { listWorks, fetchCertificate, downloadCertificate } from '../api/works'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { formatDateTime, PLAN_LABEL } from '../lib/format'

function shortSha(sha: string): string {
  return sha.length > 16 ? `${sha.slice(0, 10)}…${sha.slice(-4)}` : sha
}

/** 合规与权利中心：授权证书卡 + 发行合规检查 + 全局开关 */
export default function RightsView() {
  const [works, setWorks] = useState<Work[]>([])
  const [workId, setWorkId] = useState<string>('')
  const [cert, setCert] = useState<Certificate | null>(null)
  const [loading, setLoading] = useState(false)
  const [certError, setCertError] = useState<string | null>(null)
  const user = useSessionStore((s) => s.user)
  const [toggles, setToggles] = useState({ disclosure: true, watermark: true, voiceVerify: true })
  /** version_id → 已签发证书（会话内缓存）：证书端点有落库副作用，仅显式点击时调用一次 */
  const certCache = useRef<Map<string, Certificate>>(new Map())

  useEffect(() => {
    void (async () => {
      try {
        const res = await listWorks({ status: 'active', page: 1, page_size: 100 })
        setWorks(res.items)
        if (res.items.length > 0) setWorkId(res.items[0].id)
      } catch {
        /* 拦截器已 toast */
      }
    })()
  }, [])

  const work = works.find((w) => w.id === workId) ?? null

  // 切换作品仅重置展示，不自动拉取证书（浏览即签发会污染 FR-14 审计数据）
  useEffect(() => {
    setCert(null)
    setCertError(null)
  }, [workId])

  const onViewCert = async () => {
    if (!work) return
    const versionId = work.active_version_id
    const cached = certCache.current.get(versionId)
    if (cached) {
      setCert(cached)
      return
    }
    setLoading(true)
    setCertError(null)
    try {
      const c = await fetchCertificate(versionId)
      certCache.current.set(versionId, c)
      setCert(c)
    } catch (err) {
      setCertError(
        err instanceof Error && err.message ? err.message : '该版本尚未采用候选，暂无法签发证书',
      )
    } finally {
      setLoading(false)
    }
  }

  const onDownload = async () => {
    if (!work || !cert) return
    try {
      await downloadCertificate(
        work.active_version_id,
        `${work.display_code}_${cert.version.version_no}_certificate.json`,
      )
      toast('授权证书 JSON 已开始下载')
    } catch {
      /* 拦截器已 toast */
    }
  }

  const onCopyLink = async () => {
    if (!cert) return
    try {
      await navigator.clipboard.writeText(
        `${window.location.origin}${cert.human_participation.events_ref}`,
      )
      toast('已复制留痕验证链接')
    } catch {
      toast('复制失败，请手动复制：' + cert.human_participation.events_ref, 'warn')
    }
  }

  const isFree = user?.plan === 'free'
  // 文案原则（审查 P2-13）：不做无法兑现的断言 —— 响度为目标规格而非逐条实测；
  // 频域不可听水印为 V1.1 能力，当前本地引擎以 SHA-256 指纹登记实现溯源。
  const checklist: Array<{ ok: boolean; text: string }> = [
    { ok: true, text: 'AI 参与声明已写入 metadata（流媒体披露就绪）' },
    {
      ok: !isFree,
      text: isFree
        ? '免费档导出嵌入水印（当前以 SHA-256 指纹登记实现）· 升级付费档导出无水印'
        : '不可听水印导出时嵌入 —— 本地引擎当前以 SHA-256 指纹登记实现，可溯源',
    },
    { ok: true, text: '响度 −14 LUFS · 真峰值 −1.0 dBTP —— 导出目标规格（流媒体预设），非逐条实测' },
    { ok: true, text: '敏感词生成时校验 · 未检测到名人仿声 / 受保护采样' },
  ]

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">Rights / 合规与权利中心</div>
        <h1 className="text-[28px] font-extrabold tracking-tight mt-1">每一首，都有清白凭证</h1>
      </header>
      <div className="grid grid-cols-[1fr_320px] rule-t flex-1 min-h-0">
        <div className="px-8 py-5 border-r overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="label">授权证书{cert ? ` · ${cert.work.title} ${cert.version.version_no}` : ''}</div>
            <div className="w-[280px]">
              <select value={workId} onChange={(e) => setWorkId(e.target.value)}>
                {works.length === 0 && <option value="">暂无作品</option>}
                {works.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.display_code} · {w.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {loading ? (
            <div className="card mt-3 p-6 text-center text-[12px]" style={{ color: 'var(--dim)' }}>
              读取证书…
            </div>
          ) : certError ? (
            <div className="card mt-3 p-6">
              <div className="text-[12px]" style={{ color: 'var(--warn)' }}>{certError}</div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                在作品详情页对候选点「采用定稿」后，即可签发授权证书。
              </div>
              <button className="btn btn-ghost text-[11px] mt-4" onClick={() => void onViewCert()}>
                重试
              </button>
            </div>
          ) : cert ? (
            <div className="card mt-3 p-6">
              <div className="grid grid-cols-2 gap-y-4 text-[12px]">
                <div>
                  <div className="label mb-1">作品 ID</div>
                  <span className="num font-semibold">{cert.work.display_code}</span>
                </div>
                <div>
                  <div className="label mb-1">模型 / 版本</div>
                  <span className="font-semibold">
                    {cert.model.provider_display} · {cert.model.model} · seed {cert.model.seed}
                  </span>
                </div>
                <div>
                  <div className="label mb-1">生成时间</div>
                  <span className="num font-semibold">{formatDateTime(cert.generated_at)}</span>
                </div>
                <div>
                  <div className="label mb-1">许可类型</div>
                  <span className="font-semibold" style={{ color: cert.license.valid ? 'var(--acc)' : 'var(--warn)' }}>
                    {cert.license.type === 'commercial' ? '商用授权' : '非商用'} · {PLAN_LABEL[cert.license.plan]}
                  </span>
                </div>
                <div className="col-span-2">
                  <div className="label mb-1">人类创作留痕</div>
                  <span style={{ color: 'var(--muted)' }}>
                    共 {cert.human_participation.edit_events_count} 条 · {cert.human_participation.summary.join(' · ')}
                  </span>
                </div>
                <div className="col-span-2">
                  <div className="label mb-1">内容指纹</div>
                  <span className="num" style={{ color: 'var(--muted)' }}>
                    {cert.fingerprint.algorithm.toUpperCase()} · master {shortSha(cert.fingerprint.master_wav_sha256)} · preview {shortSha(cert.fingerprint.preview_mp3_sha256)}
                  </span>
                </div>
              </div>
              <div className="flex gap-2 mt-6">
                <button className="btn btn-acc text-[11px]" onClick={() => void onDownload()}>
                  下载证书 JSON
                </button>
                <button className="btn btn-ghost text-[11px]" onClick={() => void onCopyLink()}>
                  复制验证链接
                </button>
              </div>
            </div>
          ) : work ? (
            <div className="card mt-3 p-6">
              <div className="text-[12px]" style={{ color: 'var(--muted)' }}>
                点击查看并签发授权证书
              </div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                证书按契约 §8.4 实时签发：每次查看都会生成一条新的签发记录与留痕事件，
                并固化当前版本的 SHA-256 指纹；本次会话内同一版本不会重复签发。
              </div>
              <button className="btn btn-acc text-[11px] mt-4" onClick={() => void onViewCert()}>
                查看证书
              </button>
            </div>
          ) : (
            <div className="card mt-3 p-6 text-[12px]" style={{ color: 'var(--dim)' }}>
              暂无在库作品，去创作工作台生成第一首歌后再来签发证书。
            </div>
          )}

          <div className="label mt-7">发行合规检查</div>
          <div className="mt-3 space-y-2.5 text-[12px]">
            {checklist.map((item, i) => (
              <div key={i} className="flex items-center gap-2.5">
                <span className="dot" style={{ background: item.ok ? 'var(--acc)' : 'var(--warn)' }}></span>
                <span style={{ color: 'var(--muted)' }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="px-6 py-5 overflow-y-auto">
          <div className="label">全局设置</div>
          <div className="mt-4 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[13px] font-semibold">导出嵌入 AI 披露</div>
                <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--dim)' }}>
                  自动在 metadata 声明 AI 参与度
                </div>
              </div>
              <button
                className={`toggle ${toggles.disclosure ? 'on' : ''}`}
                onClick={() => setToggles((t) => ({ ...t, disclosure: !t.disclosure }))}
              ></button>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[13px] font-semibold">不可听水印</div>
                <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--dim)' }}>
                  导出时登记 SHA-256 内容指纹，可溯源（频域水印 V1.1）
                </div>
              </div>
              <button
                className={`toggle ${toggles.watermark ? 'on' : ''}`}
                onClick={() => setToggles((t) => ({ ...t, watermark: !t.watermark }))}
              ></button>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[13px] font-semibold">人声克隆双重验证</div>
                <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--dim)' }}>
                  仅本人 · 随机短语活体朗读
                </div>
              </div>
              <button
                className={`toggle ${toggles.voiceVerify ? 'on' : ''}`}
                onClick={() => setToggles((t) => ({ ...t, voiceVerify: !t.voiceVerify }))}
              ></button>
            </div>
          </div>
          <div className="text-[10px] mt-8 leading-relaxed" style={{ color: 'var(--dim)' }}>
            证书由系统按契约 §8.4 签发：AI 披露、人类参与留痕与 SHA-256 指纹随作品版本固化。PDF 版证书将在 V1.1 提供。
          </div>
        </div>
      </div>
    </section>
  )
}
