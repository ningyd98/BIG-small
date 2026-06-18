export function artifactEntries(artifacts: Record<string, string>): Array<{
  name: string;
  relativePath: string;
}> {
  return Object.entries(artifacts).map(([name, relativePath]) => ({
    name,
    relativePath,
  }));
}
