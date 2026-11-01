import base from "/home/ningyd/文档/ChatGPT/BIGsmall/dashboard/playwright.config.ts";
import path from "node:path";
const stage = process.env.R373_STAGE_DIR!;
export default { ...base, testDir: "/home/ningyd/文档/ChatGPT/BIGsmall/dashboard/tests/e2e", testIgnore: "**/research-evidence.spec.ts", outputDir: path.join(stage,"test-results"), reporter: [["list"],["junit", { outputFile: path.join(stage,"junit.xml") }]], webServer: (base.webServer as any[]).map(server => ({...server,cwd: "/home/ningyd/文档/ChatGPT/BIGsmall/dashboard", env: {...server.env, MODEL_CONTROL_DB:path.join(stage,"runtime/model_control.db"), SIMULATION_RUNTIME_DB:path.join(stage,"runtime/simulation_runtime.db"), DASHBOARD_ARTIFACT_ROOT:path.join(stage,"runtime")}})) };
