import { Layout } from "./components/Layout";
import { SourceDrawerProvider } from "./components/SourceDrawer";
import { PrefsProvider } from "./lib/prefs";
import { useRoute } from "./lib/router";
import { targetFromRoute } from "./lib/target";
import { Compare } from "./pages/Compare";
import { Home } from "./pages/Home";
import { Library } from "./pages/Library";
import { Places } from "./pages/Places";
import { Report } from "./pages/Report";

function Routes() {
  const { path, params } = useRoute();
  const target = targetFromRoute(path, params);
  if (target)
    return (
      <Layout active="home">
        <Report target={target} params={params} />
      </Layout>
    );
  switch (path[0]) {
    case "compare":
      return (
        <Layout active="compare">
          <Compare params={params} />
        </Layout>
      );
    case "places":
      return (
        <Layout active="places">
          <Places />
        </Layout>
      );
    case "library":
      return (
        <Layout active="library">
          <Library params={params} />
        </Layout>
      );
    default:
      return (
        <Layout active="home">
          <Home />
        </Layout>
      );
  }
}

export default function App() {
  return (
    <PrefsProvider>
      <SourceDrawerProvider>
        <Routes />
      </SourceDrawerProvider>
    </PrefsProvider>
  );
}
