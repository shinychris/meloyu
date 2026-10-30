import type { VersionTreeNode } from '../types/api'

/** 计算版本树节点深度（parent_version_id 自引用链；>20 层防御性截断）。
 *  VersionTree（工作台侧栏）与 WorkDetailView（详情页树）共用。 */
export function depthOf(nodes: VersionTreeNode[], node: VersionTreeNode): number {
  const map = new Map(nodes.map((n) => [n.id, n]))
  let depth = 0
  let cur: VersionTreeNode | undefined = node
  while (cur?.parent_version_id) {
    cur = map.get(cur.parent_version_id)
    depth++
    if (depth > 20) break
  }
  return depth
}
