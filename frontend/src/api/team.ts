import type { TeamSpaceInfo } from '../types/api'
import { apiDelete, apiGet, apiPatch, apiPost } from './client'

export function listSpaces(): Promise<{ items: TeamSpaceInfo[]; total: number }> {
  return apiGet('/team/spaces')
}

export function createSpace(name: string): Promise<TeamSpaceInfo> {
  return apiPost<TeamSpaceInfo>('/team/spaces', { name })
}

export function addMember(spaceId: string, email: string, role: string): Promise<TeamSpaceInfo> {
  return apiPost(`/team/spaces/${spaceId}/members`, { email, role })
}

export function changeMemberRole(spaceId: string, memberUserId: string, role: string): Promise<TeamSpaceInfo> {
  return apiPatch(`/team/spaces/${spaceId}/members/${memberUserId}`, { role })
}

export function removeMember(spaceId: string, memberUserId: string): Promise<TeamSpaceInfo> {
  return apiDelete(`/team/spaces/${spaceId}/members/${memberUserId}`)
}

export function shareWork(workId: string, spaceId: string): Promise<{ work_id: string; space_id: string }> {
  return apiPost(`/works/${workId}/share`, { space_id: spaceId })
}

export function unshareWork(workId: string): Promise<{ work_id: string; space_id: null }> {
  return apiDelete(`/works/${workId}/share`)
}
