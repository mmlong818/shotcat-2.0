export function getProjectChaptersPath(projectId: string) {
  return `/projects/${projectId}/chapters`
}

export function getChapterStudioPath(projectId: string, chapterId: string) {
  return `/projects/${projectId}/chapters/${chapterId}/studio`
}

export function getChapterShotsPath(projectId: string, chapterId: string) {
  return `/projects/${projectId}/chapters/${chapterId}/shots`
}

export function getChapterShotEditPath(projectId: string, chapterId: string, shotId: string) {
  return `/projects/${projectId}/chapters/${chapterId}/shots/${shotId}/edit`
}

export function getProjectEditorPath(projectId: string) {
  return `/projects/${projectId}/editor`
}

