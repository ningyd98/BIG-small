from pathlib import Path
from fastapi import FastAPI
import uvicorn
from cloud_edge_robot_arm.cloud.api.research_results import router
app = FastAPI()
app.include_router(router)
app.state.research_artifact_root = Path(__file__).parent / "fixture"
app.state.research_runs_registry = {
    "software-smoke-600": {"runs_path": "runs", "protocol_path": "protocol", "analysis_path": "saved"},
    "missing-source": {"runs_path": "absent", "protocol_path": "absent", "analysis_path": "absent"},
}
@app.get("/health")
def health():
    return {"ok": True, "scope": "SOFTWARE_ONLY_BROWSER_VERIFICATION"}
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8123, log_level="warning")
