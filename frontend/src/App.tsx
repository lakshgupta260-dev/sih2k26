import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth, RequireRole } from "@/routes/guards";
import { AppShell } from "@/components/layout/AppShell";
import { ProjectLayout } from "@/components/layout/ProjectLayout";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { Landing } from "@/pages/Landing";
import { Register } from "@/pages/Register";
import { NotFound, Unauthorized } from "@/pages/Misc";
import { Projects } from "@/pages/Projects";
import { Notifications } from "@/pages/Notifications";
import { Profile } from "@/pages/Profile";
import { AdminUsers } from "@/pages/admin/AdminUsers";
import { ProjectOverview } from "@/pages/project/Overview";
import { Schedule } from "@/pages/project/Schedule";
import { ScheduleDetail } from "@/pages/project/ScheduleDetail";
import { ActivityDetail } from "@/pages/project/ActivityDetail";
import { Uploads } from "@/pages/project/Uploads";
import { Matching } from "@/pages/project/Matching";
import { Risks } from "@/pages/project/Risks";
import { Reports } from "@/pages/project/Reports";
import { Members } from "@/pages/project/Members";
import { Settings } from "@/pages/project/Settings";
import { Channels } from "@/pages/project/Channels";

export default function App() {
  return (
    <>
      <CommandPalette />
      <Routes>
        <Route path="/login" element={<Landing />} />
        <Route path="/register" element={<Register />} />
        <Route path="/unauthorized" element={<Unauthorized />} />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/projects" replace />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/profile" element={<Profile />} />
          <Route
            path="/admin/users"
            element={
              <RequireRole roles={["ADMIN"]}>
                <AdminUsers />
              </RequireRole>
            }
          />

          <Route path="/projects/:projectId" element={<ProjectLayout />}>
            <Route index element={<ProjectOverview />} />
            <Route path="schedule" element={<Schedule />} />
            <Route path="schedule/:scheduleId" element={<ScheduleDetail />} />
            <Route path="activities/:scheduleId/:activityId" element={<ActivityDetail />} />
            <Route path="uploads" element={<Uploads />} />
            <Route path="matching" element={<Matching />} />
            <Route path="risks" element={<Risks />} />
            <Route path="reports" element={<Reports />} />
            <Route path="channels" element={<Channels />} />
            <Route path="members" element={<Members />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}
