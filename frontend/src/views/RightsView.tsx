import { useEffect, useRef, useState } from 'react'
import type { Certificate, Work } from '../types/api'
import { listWorks, fetchCertificate, downloadCertificate } from '../api/works'
import { useSessionStore } from '../stores/session'
import { toast } from '../stores/toast'
import { formatDateTime, planLabel } from '../lib/format'
import { useT } from '../i18n'

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

  const isFree = user?.plan === 'free'
  // 文案原则（审查 P2-13）：不做无法兑现的断言 —— 响度为目标规格而非逐条实测；
  // 频域不可听水印为 V1.1 能力，当前本地引擎以 SHA-256 指纹登记实现溯源。
  const checklist: Array<{ ok: boolean; text: string }> = [
    { ok: true, text: t('rights.check.disclosure') },
    {
      ok: !isFree,
      text: isFree ? t('rights.check.watermarkFree') : t('rights.check.watermarkPaid'),
    },
    { ok: true, text: t('rights.check.loudness') },
    { ok: true, text: t('rights.check.safety') },
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
                <span className="dot" style={{ background: item.ok ? 'var(--acc)' : 'var(--warn)' }}></span>
                <span style={{ color: 'var(--muted)' }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="px-6 py-5 overflow-y-auto">
          <div className="label">{t('rights.settings')}</div>
          <div className="mt-4 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[13px] font-semibold">{t('rights.setting.disclosure')}</div>
                <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--dim)' }}>
                  {t('rights.setting.disclosureDesc')}
                </div>
              </div>
              <button
                className={`toggle ${toggles.disclosure ? 'on' : ''}`}
                onClick={() => setToggles((t) => ({ ...t, disclosure: !t.disclosure }))}
              ></button>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[13px] font-semibold">{t('rights.setting.watermark')}</div>
                <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--dim)' }}>
                  {t('rights.setting.watermarkDesc')}
                </div>
              </div>
              <button
                className={`toggle ${toggles.watermark ? 'on' : ''}`}
                onClick={() => setToggles((t) => ({ ...t, watermark: !t.watermark }))}
              ></button>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[13px] font-semibold">{t('rights.setting.voiceVerify')}</div>
                <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--dim)' }}>
                  {t('rights.setting.voiceVerifyDesc')}
                </div>
              </div>
              <button
                className={`toggle ${toggles.voiceVerify ? 'on' : ''}`}
                onClick={() => setToggles((t) => ({ ...t, voiceVerify: !t.voiceVerify }))}
              ></button>
            </div>
          </div>
          <div className="text-[10px] mt-8 leading-relaxed" style={{ color: 'var(--dim)' }}>
            {t('rights.settingsNote')}
          </div>
        </div>
      </div>
    </section>
  )
}
