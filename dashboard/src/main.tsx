import React from "react"
import ReactDOM from "react-dom/client"
import { createBrowserRouter, RouterProvider } from "react-router-dom"
import Launcher from "./routes/Launcher"
import RunView from "./routes/RunView"
import VerdictDrilldown from "./routes/VerdictDrilldown"
import "./index.css"

const router = createBrowserRouter([
  { path: "/", element: <Launcher /> },
  { path: "/runs/:id", element: <RunView /> },
  { path: "/runs/:id/verdicts/:vid", element: <VerdictDrilldown /> },
])
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><RouterProvider router={router} /></React.StrictMode>,
)
