import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { Spinner } from "./components/ui";
import TopNav from "./components/TopNav";
import Atlas from "./pages/Atlas";
import Briefing from "./pages/Briefing";
import Desk from "./pages/Desk";
import Drills from "./pages/Drills";
import Journal from "./pages/Journal";
import Playbook from "./pages/Playbook";
import Progress from "./pages/Progress";
import SettingsPage from "./pages/Settings";
import Wrapup from "./pages/Wrapup";

// The workbench pulls in Monaco + xterm; load it on demand.
const Workbench = lazy(() => import("./workbench/Workbench"));

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="surface-glow flex min-h-full flex-col">
      <TopNav />
      <main className="flex-1">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/e/:eid"
        element={
          <Suspense fallback={<div className="grid h-full place-items-center"><Spinner className="size-6" /></div>}>
            <Workbench />
          </Suspense>
        }
      />
      <Route path="/e/:eid/wrapup" element={<Shell><Wrapup /></Shell>} />
      <Route path="/case/:caseId" element={<Shell><Briefing /></Shell>} />
      <Route path="/atlas" element={<Shell><Atlas /></Shell>} />
      <Route path="/journal" element={<Shell><Journal /></Shell>} />
      <Route path="/drills" element={<Shell><Drills /></Shell>} />
      <Route path="/progress" element={<Shell><Progress /></Shell>} />
      <Route path="/playbook" element={<Shell><Playbook /></Shell>} />
      <Route path="/playbook/:slug" element={<Shell><Playbook /></Shell>} />
      <Route path="/settings" element={<Shell><SettingsPage /></Shell>} />
      <Route path="*" element={<Shell><Desk /></Shell>} />
    </Routes>
  );
}
