import { apiGet } from './client'
import type { UsageStats } from '../types/api'

/** GET /usage/stats —— 用量统计与分析（按天/按引擎通道）。
 *  v0.17.0：license（桌面买断）模式下用量为纯计量——本地软件不消耗任何
 *  官方积分，云端通道的用量对应你自己配置的 API Key。 */
export function getUsageStats(days = 30): Promise<UsageStats> {
  return apiGet<UsageStats>('/usage/stats', { days })
}
