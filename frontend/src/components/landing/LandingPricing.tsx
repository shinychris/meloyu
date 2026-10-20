import { useNavigate } from 'react-router-dom'
import { LICENSE_SKU } from '../../lib/landing-data'
import { useT } from '../../i18n'
import { EqMark } from './EqMark'
import { useSiteMode } from './SiteMode'

/** 折扣百分比（sale < price 时有效；无折扣回 null → 单价格局，划线/徽标隐藏） */
const DISCOUNT_PCT =
  LICENSE_SKU.price > LICENSE_SKU.salePrice && LICENSE_SKU.salePrice > 0
    ? Math.round(((LICENSE_SKU.price - LICENSE_SKU.salePrice) / LICENSE_SKU.price) * 100)
    : null

/** 定价：单档终身授权买断（D-1 定案：$399 终身原价锚，限时买断价 $129；无免费层、无订阅） */
export default function LandingPricing() {
  const navigate = useNavigate()
  const t = useT()
  const site = useSiteMode()
  return (
    <section id="pricing" className="scroll-mt-20">
      <div className="label flex items-center gap-2"><EqMark />{t('landing.pricing.label')}</div>
      <h2 className="text-2xl font-extrabold tracking-tight mt-2">{t('landing.pricing.title')}</h2>
      <p className="text-base mt-2 max-w-[560px] text-muted">
        {t('landing.pricing.desc')}
      </p>
      <div className="max-w-[440px] mt-8 relative border border-line-2" style={{ background: 'var(--bg2)', boxShadow: 'inset 0 2px 0 var(--acc)' }}>
        {DISCOUNT_PCT != null && (
          <div className="badge badge-solid absolute top-0 right-0">
            {t(LICENSE_SKU.badge)} · -{DISCOUNT_PCT}%
          </div>
        )}
        <div className="p-6 flex flex-col">
          <div className="label" style={{ color: 'var(--acc)' }}>
            {t(LICENSE_SKU.name)}
          </div>
          <div className="price-num mt-4 flex items-baseline gap-3 flex-wrap">
            <span>${(LICENSE_SKU.salePrice / 100).toFixed(0)}</span>
            {DISCOUNT_PCT != null && (
              <span className="text-base font-bold text-dim line-through">
                ${(LICENSE_SKU.price / 100).toFixed(0)}
              </span>
            )}
            <span className="text-base font-bold text-muted">
              {t('landing.pricing.oneTime')}
            </span>
          </div>
          <div className="text-xs mt-1.5 text-dim">
            {t(LICENSE_SKU.tagline)} · {t(LICENSE_SKU.platforms)}
          </div>
          <ul className="mt-5 space-y-2 flex-1">
            {LICENSE_SKU.features.map((f) => (
              <li key={f} className="text-sm leading-relaxed flex gap-2 text-muted">
                <span style={{ color: 'var(--acc)' }}>·</span>
                {t(f)}
              </li>
            ))}
          </ul>
          {/* 官网站点直链 /buy（portal → Stripe Payment Link）；App 内过渡期指登录入口，
              P3 购买通道全量后统一外链 */}
          {site ? (
            <a className="btn btn-acc w-full mt-6 block text-center" href="/buy">
              {t('landing.pricing.cta.buy')}
            </a>
          ) : (
            <button className="btn btn-acc w-full mt-6" onClick={() => navigate('/login')}>
              {t('landing.pricing.cta.buy')}
            </button>
          )}
        </div>
      </div>
      <p className="text-xs mt-4 text-dim">
        {t('landing.pricing.footnote')}
      </p>
    </section>
  )
}
