import type { QueryClient } from "@tanstack/react-query";
import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";

import { HospitalLayout } from "@/layouts/hospital-layout";
import { OpsLayout } from "@/layouts/ops-layout";
import { PublicLayout } from "@/layouts/public-layout";
import { RespondLayout } from "@/layouts/respond-layout";
import { authStore, homeFor, surfaceFor, type Surface } from "@/lib/auth-store";
import { LoginPage } from "@/pages/login-page";
import { NotFound } from "@/pages/not-found";
import { CameraWall } from "@/pages/ops/camera-wall";
import { DesignSystemPage } from "@/pages/ops/design-system-page";
import { ConsolePage } from "@/pages/ops/console-page";
import { IncidentDetailPage } from "@/pages/ops/incident/incident-detail-page";
import { SystemPage } from "@/pages/ops/system-page";
import { PlaceholderPage } from "@/pages/placeholder-page";
import { PublicHome } from "@/pages/public/public-home";
import { ReportPage } from "@/pages/public/report-page";
import { TryLivePage } from "@/pages/public/try-live-page";
import { TryPage } from "@/pages/public/try-page";

export type RouterContext = { queryClient: QueryClient };

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
  notFoundComponent: NotFound,
});

/** Signed out goes to `/login`; signed in with another role goes to its own surface. */
function requireSurface(surface: Surface) {
  return () => {
    const session = authStore.current();
    if (!session) throw redirect({ to: "/login", replace: true });
    if (surfaceFor(session.user.role) !== surface) {
      throw redirect({ to: homeFor(session.user.role), replace: true });
    }
  };
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    const session = authStore.current();
    throw redirect({ to: session ? homeFor(session.user.role) : "/login", replace: true });
  },
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  beforeLoad: () => {
    const session = authStore.current();
    if (session) throw redirect({ to: homeFor(session.user.role), replace: true });
  },
  component: LoginPage,
});

// ---- operator console: operator, supervisor, auditor, admin
const opsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/ops",
  beforeLoad: requireSurface("ops"),
  component: OpsLayout,
});
const opsRoutes = [
  createRoute({ getParentRoute: () => opsRoute, path: "/", component: ConsolePage }),
  createRoute({
    getParentRoute: () => opsRoute,
    path: "incidents",
    beforeLoad: () => {
      throw redirect({ to: "/ops", replace: true });
    },
  }),
  createRoute({
    getParentRoute: () => opsRoute,
    path: "incidents/$incidentId",
    component: IncidentDetailPage,
  }),
  createRoute({ getParentRoute: () => opsRoute, path: "cameras", component: CameraWall }),
  createRoute({ getParentRoute: () => opsRoute, path: "system", component: SystemPage }),
  createRoute({ getParentRoute: () => opsRoute, path: "design", component: DesignSystemPage }),
];

// ---- responder app
const respondRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/respond",
  beforeLoad: requireSurface("respond"),
  component: RespondLayout,
});
const respondRoutes = [
  createRoute({
    getParentRoute: () => respondRoute,
    path: "/",
    component: () => <PlaceholderPage pageKey="respond.incidents" />,
  }),
  createRoute({
    getParentRoute: () => respondRoute,
    path: "profile",
    component: () => <PlaceholderPage pageKey="respond.profile" />,
  }),
];

// ---- hospital view
const hospitalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/hospital",
  beforeLoad: requireSurface("hospital"),
  component: HospitalLayout,
});
const hospitalRoutes = [
  createRoute({
    getParentRoute: () => hospitalRoute,
    path: "/",
    component: () => <PlaceholderPage pageKey="hospital.incoming" />,
  }),
];

// ---- public pages (no login)
const publicRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/public",
  component: PublicLayout,
});
const publicRoutes = [
  createRoute({ getParentRoute: () => publicRoute, path: "/", component: PublicHome }),
  createRoute({
    getParentRoute: () => publicRoute,
    path: "report",
    component: ReportPage,
  }),
  createRoute({
    getParentRoute: () => publicRoute,
    path: "try",
    component: TryPage,
  }),
  createRoute({
    getParentRoute: () => publicRoute,
    path: "try/live",
    component: TryLivePage,
  }),
  createRoute({
    getParentRoute: () => publicRoute,
    path: "privacy",
    component: () => <PlaceholderPage pageKey="public.privacy" />,
  }),
];

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  opsRoute.addChildren(opsRoutes),
  respondRoute.addChildren(respondRoutes),
  hospitalRoute.addChildren(hospitalRoutes),
  publicRoute.addChildren(publicRoutes),
]);

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
