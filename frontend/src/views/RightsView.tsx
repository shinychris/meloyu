import { useEffect, useRef, useState } from 'react'
import type { Certificate, Work } from '../types/api'
import { listWorks, fetchCertificate, downloadCertificate } from '../api/works'
import { toast } from '../stores/toast'
import { formatDateTime, planLabel } from '../lib/format'
import { useT } from '../i18n'

function shortSha(sha: string): string {
  return sha.length > 16 ? `${sha.slice(0, 10)}…${sha.slice(-4)}` : sha
}

/** 合规与权利中心：授权证书卡 + 真实数据驱动的发行合规检查 + 静态授权说明（v0.7.0 去虚还实） */
export default function RightsView() {
  const [works, setWorks] = useState<Work[]>([])
  const [workId, setWorkId] = useState<string>('')
  const [cert, setCert] = useState<Certificate | null>(null)
  const [loading, setLoading] = useState(false)
  const [certError, setCertError] = useState<string | null>(null)
  /** version_id → 已签发证书（会话内缓存）：证书端点有落库副作用，仅显式点击时调用一次 */
  const certCache = useRef<Map<string, Certificate>>(new Map())
  const t = useT()

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
        err instanceof Error && err.message ? err.message : t('rights.cert.errorNotAdopted'),
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
      toast(t('rights.cert.downloadStarted'))
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
      toast(t('rights.cert.linkCopied'))
    } catch {
      toast(t('rights.cert.copyFailed', { link: cert.human_participation.events_ref }), 'warn')
    }
  }

  /**
   * v0.7.0「去虚还实」：checklist 改为真实数据驱动，只陈述实际存在的能力 ——
   * AI 披露与 SHA-256 指纹已随证书真实落库（绿点）；−14 LUFS 是导出目标规格而非
   * 逐项实测（灰色信息项，不打绿勾）；内容安全目前是基础敏感词过滤（黄点，如实）。
   */
  const CHECK_TONE: Record<'ok' | 'warn' | 'info', string> = {
    ok: 'var(--acc)',
    warn: 'var(--warn)',
    info: 'var(--dim)',
  }
  const checklist: Array<{ tone: 'ok' | 'warn' | 'info'; text: string }> = [
    { tone: 'ok', text: t('rights.check.disclosure') },
    { tone: 'ok', text: t('rights.check.fingerprint') },
    { tone: 'info', text: t('rights.check.loudness') },
    { tone: 'warn', text: t('rights.check.safety') },
  ]

  return (
    <section className="view flex flex-col h-full">
      <header className="px-8 pt-6 pb-4">
        <div className="label">{t('rights.label')}</div>
        <h1 className="text-[28px] font-extrabold tracking-tight mt-1">{t('rights.title')}</h1>
      </header>
      <div className="grid grid-cols-[1fr_320px] rule-t flex-1 min-h-0">
        <div className="px-8 py-5 border-r overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="label">{t('rights.cert.cardTitle')}{cert ? ` · ${cert.work.title} ${cert.version.version_no}` : ''}</div>
            <div className="w-[280px]">
              <select value={workId} onChange={(e) => setWorkId(e.target.value)}>
                {works.length === 0 && <option value="">{t('rights.cert.noWorks')}</option>}
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
              {t('rights.cert.loading')}
            </div>
          ) : certError ? (
            <div className="card mt-3 p-6">
              <div className="text-[12px]" style={{ color: 'var(--warn)' }}>{certError}</div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('rights.cert.errorHint')}
              </div>
              <button className="btn btn-ghost text-[11px] mt-4" onClick={() => void onViewCert()}>
                {t('common.retry')}
              </button>
            </div>
          ) : cert ? (
            <div className="card mt-3 p-6">
              <div className="grid grid-cols-2 gap-y-4 text-[12px]">
                <div>
                  <div className="label mb-1">{t('rights.field.workId')}</div>
                  <span className="num font-semibold">{cert.work.display_code}</span>
                </div>
                <div>
                  <div className="label mb-1">{t('rights.field.modelVersion')}</div>
                  <span className="font-semibold">
                    {cert.model.provider_display} · {cert.model.model} · seed {cert.model.seed}
                  </span>
                </div>
                <div>
                  <div className="label mb-1">{t('rights.field.generatedAt')}</div>
                  <span className="num font-semibold">{formatDateTime(cert.generated_at)}</span>
                </div>
                <div>
                  <div className="label mb-1">{t('rights.field.licenseType')}</div>
                  <span className="font-semibold" style={{ color: cert.license.valid ? 'var(--acc)' : 'var(--warn)' }}>
                    {cert.license.type === 'commercial' ? t('rights.license.commercial') : t('rights.license.nonCommercial')} · {planLabel(cert.license.plan)}
                  </span>
                </div>
                <div className="col-span-2">
                  <div className="label mb-1">{t('rights.field.humanTrail')}</div>
                  <span style={{ color: 'var(--muted)' }}>
                    {t('rights.trail.count', { n: cert.human_participation.edit_events_count })} · {cert.human_participation.summary.join(' · ')}
                  </span>
                </div>
                <div className="col-span-2">
                  <div className="label mb-1">{t('rights.field.fingerprint')}</div>
                  <span className="num" style={{ color: 'var(--muted)' }}>
                    {cert.fingerprint.algorithm.toUpperCase()} · master {shortSha(cert.fingerprint.master_wav_sha256)} · preview {shortSha(cert.fingerprint.preview_mp3_sha256)}
                  </span>
                </div>
              </div>
              <div className="flex gap-2 mt-6">
                <button className="btn btn-acc text-[11px]" onClick={() => void onDownload()}>
                  {t('rights.cert.download')}
                </button>
                <button className="btn btn-ghost text-[11px]" onClick={() => void onCopyLink()}>
                  {t('rights.cert.copyLink')}
                </button>
              </div>
            </div>
          ) : work ? (
            <div className="card mt-3 p-6">
              <div className="text-[12px]" style={{ color: 'var(--muted)' }}>
                {t('rights.cert.viewHint')}
              </div>
              <div className="text-[11px] mt-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
                {t('rights.cert.realtimeNote')}
              </div>
              <button className="btn btn-acc text-[11px] mt-4" onClick={() => void onViewCert()}>
                {t('rights.cert.view')}
              </button>
            </div>
          ) : (
            <div className="card mt-3 p-6 text-[12px]" style={{ color: 'var(--dim)' }}>
              {t('rights.empty')}
            </div>
          )}

          <div className="label mt-7">{t('rights.check.title')}</div>
          <div className="mt-3 space-y-2.5 text-[12px]">
            {checklist.map((item, i) => (
              <div key={i} className="flex items-center gap-2.5">
                <span className="dot flex-none" style={{ background: CHECK_TONE[item.tone] }}></span>
                <span style={{ color: 'var(--muted)' }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* v0.7.0：原三个摆设开关整段下架，改为静态授权说明（商用权利跟随通道模型许可） */}
        <div className="px-6 py-5 overflow-y-auto">
          <div className="label">{t('rights.licenseNotes.title')}</div>
          <div className="mt-4 space-y-3 text-[12px] leading-relaxed" style={{ color: 'var(--muted)' }}>
            <div>{t('rights.licenseNotes.intro')}</div>
            <div>· {t('rights.licenseNotes.commercial')}</div>
            <div>· {t('rights.licenseNotes.nonCommercial')}</div>
            <div>· {t('rights.licenseNotes.conditional')}</div>
          </div>
          <div className="text-[10px] mt-8 leading-relaxed" style={{ color: 'var(--dim)' }}>
            {t('rights.settingsNote')}
          </div>
        </div>
      </div>
    </section>
  )
}
