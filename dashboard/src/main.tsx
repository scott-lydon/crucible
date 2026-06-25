import React from "react"
import ReactDOM from "react-dom/client"
import { createBrowserRouter, RouterProvider } from "react-router-dom"
import Launcher from "./routes/Launcher"
import Runs from "./routes/Runs"
import RunView from "./routes/RunView"
import VerdictDrilldown from "./routes/VerdictDrilldown"
import MetricsView from "./routes/Metrics"
import Catalog from "./routes/Catalog"
import BlueReview from "./routes/BlueReview"
import Health from "./routes/Health"
import AdminDebug from "./routes/AdminDebug"
import "./index.css"

const router = createBrowserRouter([
  { path: "/", element: <Launcher /> },
  { path: "/runs", element: <Runs /> },
  { path: "/runs/:id", element: <RunView /> },
  { path: "/runs/:id/verdicts/:vid", element: <VerdictDrilldown /> },
  { path: "/metrics", element: <MetricsView /> },
  { path: "/catalog", element: <Catalog /> },
  { path: "/blue", element: <BlueReview /> },
  { path: "/blue/:patchId", element: <BlueReview /> },
  { path: "/health", element: <Health /> },
  { path: "/admin/debug", element: <AdminDebug /> },
])

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
