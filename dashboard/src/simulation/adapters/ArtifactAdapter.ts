// artifact 适配器，负责脱敏路径和统一证据文件展示字段。
export function artifactEntries(artifacts: Record<string, string>): Array<{
  name: string;
  relativePath: string;
}> {
  return Object.entries(artifacts).map(([name, relativePath]) => ({
    name,
    relativePath,
  }));
}
