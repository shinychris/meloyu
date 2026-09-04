/**
 * zh 字典合并入口。类型受 Record<TranslationKey, string> 约束 ——
 * en 里有而 zh 里缺的 key 会在 typecheck 阶段报错。
 */
import { en } from '../en'
import { commonZh } from './common'
import { appZh } from './app'
import { landingZh } from './landing'
import { studioZh } from './studio'
import { lyricsZh } from './lyrics'
import { libraryZh } from './library'
import { workZh } from './work'
import { rightsZh } from './rights'
import { pricingZh } from './pricing'
import { modelsZh } from './models'
import { loginZh } from './login'
import { layoutZh } from './layout'
import { authZh } from './auth'
import { billingZh } from './billing'
import { editorZh } from './editor'

export const zh: Record<keyof typeof en, string> = {
  ...commonZh,
  ...appZh,
  ...landingZh,
  ...studioZh,
  ...lyricsZh,
  ...libraryZh,
  ...workZh,
  ...rightsZh,
  ...pricingZh,
  ...modelsZh,
  ...loginZh,
  ...layoutZh,
  ...authZh,
  ...billingZh,
  ...editorZh,
}
