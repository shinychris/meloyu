/** rights 命名空间：合规与权利中心（RightsView） */
export const rightsEn = {
  // 页头
  'rights.label': 'Rights / Compliance & Rights Center',
  'rights.title': 'Every song comes with clean provenance',
  // 授权证书卡
  'rights.cert.cardTitle': 'License Certificate',
  'rights.cert.noWorks': 'No works yet',
  'rights.cert.loading': 'Loading certificate…',
  'rights.cert.viewHint': 'Click to view and issue the license certificate',
  'rights.cert.realtimeNote':
    'Certificates are issued in real time per contract §8.4: each view creates a new issuance record and audit-trail event, and freezes the SHA-256 fingerprint of the current version; the same version is not issued twice within this session.',
  'rights.cert.errorNotAdopted': 'This version has no adopted candidate yet, so no certificate can be issued',
  'rights.cert.errorHint':
    'Adopt a candidate as the final version on the work detail page, then the license certificate can be issued.',
  'rights.cert.view': 'View certificate',
  'rights.cert.download': 'Download certificate JSON',
  'rights.cert.downloadStarted': 'Certificate JSON download started',
  'rights.cert.copyLink': 'Copy verification link',
  'rights.cert.linkCopied': 'Verification link copied',
  'rights.cert.copyFailed': 'Copy failed — please copy manually: {link}',
  // 证书字段
  'rights.field.workId': 'Work ID',
  'rights.field.modelVersion': 'Model / Version',
  'rights.field.generatedAt': 'Generated at',
  'rights.field.licenseType': 'License type',
  'rights.field.humanTrail': 'Human creative audit trail',
  'rights.field.fingerprint': 'Content fingerprint',
  'rights.license.commercial': 'Commercial license',
  'rights.license.nonCommercial': 'Non-commercial',
  'rights.trail.count': '{n} events in total',
  // 空状态
  'rights.empty':
    'No works in your library yet — create your first song in the Studio, then come back to issue a certificate.',
  // 发行合规检查
  'rights.check.title': 'Release compliance check',
  'rights.check.disclosure': 'AI participation statement written into metadata (ready for streaming disclosure)',
  'rights.check.watermarkFree':
    'Free-plan exports embed a watermark (currently via SHA-256 fingerprint registration) · paid plans export watermark-free',
  'rights.check.watermarkPaid':
    'Inaudible watermark embedded on export — the local engine currently implements this via SHA-256 fingerprint registration, traceable to the source',
  'rights.check.loudness':
    'Loudness −14 LUFS · true peak −1.0 dBTP — export target spec (streaming preset), not measured per track',
  'rights.check.safety': 'Sensitive-word check at generation · no celebrity voice imitation or protected samples detected',
  // 全局设置
  'rights.settings': 'Global settings',
  'rights.setting.disclosure': 'Embed AI disclosure on export',
  'rights.setting.disclosureDesc': 'Automatically declares AI participation in metadata',
  'rights.setting.watermark': 'Inaudible watermark',
  'rights.setting.watermarkDesc':
    'Registers a SHA-256 content fingerprint on export for traceability (spectral watermark lands in V1.1)',
  'rights.setting.voiceVerify': 'Voice-clone dual verification',
  'rights.setting.voiceVerifyDesc': 'Owner only · random passphrase liveness reading',
  'rights.settingsNote':
    'Certificates are issued by the system per contract §8.4: AI disclosure, human participation audit trail and SHA-256 fingerprint are frozen with each work version. PDF certificates arrive in V1.1.',
} as const
