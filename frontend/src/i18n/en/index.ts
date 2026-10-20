/**
 * en 字典合并入口（默认语言）。TranslationKey 由本对象推导；
 * 新增文案请填充各模块文件，不要在这里直接加 key。
 */
import { commonEn } from './common'
import { appEn } from './app'
import { landingEn } from './landing'
import { studioEn } from './studio'
import { lyricsEn } from './lyrics'
import { libraryEn } from './library'
import { workEn } from './work'
import { rightsEn } from './rights'
import { pricingEn } from './pricing'
import { modelsEn } from './models'
import { settingsEn } from './settings'
import { loginEn } from './login'
import { layoutEn } from './layout'
import { authEn } from './auth'
import { licenseEn } from './license'
import { editorEn } from './editor'
import { editEn } from './edit'
import { pitchEn } from './pitch'
import { marketEn } from './market'

export const en = {
  ...commonEn,
  ...appEn,
  ...landingEn,
  ...studioEn,
  ...lyricsEn,
  ...libraryEn,
  ...workEn,
  ...rightsEn,
  ...pricingEn,
  ...modelsEn,
  ...settingsEn,
  ...loginEn,
  ...layoutEn,
  ...authEn,
  ...licenseEn,
  ...editorEn,
  ...editEn,
  ...pitchEn,
  ...marketEn,
} as const
