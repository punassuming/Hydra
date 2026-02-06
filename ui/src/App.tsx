import { useMemo, useState } from "react";
import { Layout, Typography, Space, Menu, Switch as AntSwitch, Tag } from "antd";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import { HomePage } from "./pages/Home";
import { BrowsePage } from "./pages/Browse";
import { ComingSoon } from "./pages/ComingSoon";
import { JobDetailPage } from "./pages/JobDetail";
import { HistoryPage } from "./pages/History";
import { StatusPage } from "./pages/Status";
import { WorkersPage } from "./pages/Workers";
import { AdminPage } from "./pages/Admin";
import { HydraLogo } from "./components/HydraLogo";
import { DomainSelector } from "./components/DomainSelector";
import { AuthPrompt } from "./components/AuthPrompt";
import { hasAnyToken } from "./api/client";
import { WorkerDetailPage } from "./pages/WorkerDetail";
import { ActiveDomainProvider, useActiveDomain } from "./context/ActiveDomainContext";
import { ThemeProvider, useTheme } from "./theme";

function AppShell({ darkMode, setDarkMode }: { darkMode: boolean; setDarkMode: (dark: boolean) => void }) {
  const location = useLocation();
  const [authOpen, setAuthOpen] = useState(!hasAnyToken());
  const { domain: activeDomain, setDomain: setActiveDomain } = useActiveDomain();
  const { colors } = useTheme();
  const { Header, Content } = Layout;
  const menuItems = useMemo(
    () => [
      {
        label: "Operate",
        key: "operate",
        children: [
          { label: <Link to="/">Jobs</Link>, key: "operate-home" },
          { label: <Link to="/browse">Job Browser</Link>, key: "operate-browse" },
          { label: <Link to="/workers">Workers</Link>, key: "operate-workers" },
        ],
      },
      {
        label: "Observe",
        key: "observe",
        children: [
          { label: <Link to="/status">Status</Link>, key: "observe-status" },
          { label: <Link to="/history">History</Link>, key: "observe-history" },
        ],
      },
      { label: <Link to="/admin">Admin</Link>, key: "admin" },
    ],
    [],
  );

  const currentKey = useMemo(() => {
    if (location.pathname.startsWith("/status")) return "observe-status";
    if (location.pathname.startsWith("/history")) return "observe-history";
    if (location.pathname.startsWith("/browse")) return "operate-browse";
    if (location.pathname.startsWith("/workers")) return "operate-workers";
    if (location.pathname.startsWith("/admin")) return "admin";
    return "operate-home";
  }, [location.pathname]);

  return (
    <ConfigProvider
      theme={{
        algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: colors.primary,
          borderRadius: 6,
        },
      }}
    >
      <Layout>
        <Header
          style={{
            padding: "12px 24px",
            minHeight: 72,
            lineHeight: "normal",
            position: "sticky",
            top: 0,
            zIndex: 1000,
            width: "100%",
            background: colors.headerBg,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <Space align="center" wrap>
              <HydraLogo size={40} color={colors.primary} />
              <Space size={12} align="baseline" style={{ flexWrap: "wrap" }}>
                <Typography.Title
                  level={3}
                  style={{ color: colors.textPrimary, margin: 0, fontSize: "clamp(16px, 4vw, 24px)" }}
                >
                  Hydra Scheduler
                </Typography.Title>
                <Typography.Text 
                  style={{ 
                    color: colors.textSecondary, 
                    fontSize: "clamp(12px, 2vw, 14px)"
                  }}
                  className="hide-on-mobile"
                >
                  Jobs, tasks, and insights at a glance
                </Typography.Text>
              </Space>
            </Space>
            <Space align="center" size="large" style={{ flexWrap: "wrap" }}>
              <Menu
                theme="dark"
                mode="horizontal"
                selectedKeys={[currentKey]}
                items={menuItems}
                style={{ 
                  background: "transparent", 
                  borderBottom: "none"
                }}
                className="responsive-menu"
              />
              <Space size={12} align="center" wrap>
                <Tag color="cyan" style={{ marginRight: 0 }}>
                  Domain: {activeDomain}
                </Tag>
                <DomainSelector onChange={setActiveDomain} />
              </Space>
              <Space wrap>
                <Typography.Text style={{ color: colors.textSecondary, fontSize: "14px" }}>
                  Dark Mode
                </Typography.Text>
                <AntSwitch checked={darkMode} onChange={setDarkMode} />
              </Space>
            </Space>
          </div>
        </Header>
        <Content
          style={{ 
            background: colors.bgSecondary,
            minHeight: "calc(100vh - 72px)"
          }}
          className="main-content"
        >
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/status" element={<StatusPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route
              path="/browse"
              element={<BrowsePage />}
            />
            <Route path="/workers" element={<WorkersPage />} />
            <Route path="/workers/:workerId" element={<WorkerDetailPage />} />
            <Route
              path="/admin"
              element={<AdminPage />}
            />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          </Routes>
        </Content>
        <AuthPrompt open={authOpen} onClose={() => setAuthOpen(false)} onSuccess={() => setAuthOpen(false)} />
      </Layout>
    </ConfigProvider>
  );
}

export default function App() {
  const [darkMode, setDarkMode] = useState(false);
  
  return (
    <ActiveDomainProvider>
      <ThemeProvider isDarkMode={darkMode}>
        <AppShellWrapper darkMode={darkMode} setDarkMode={setDarkMode} />
      </ThemeProvider>
    </ActiveDomainProvider>
  );
}

function AppShellWrapper({ darkMode, setDarkMode }: { darkMode: boolean; setDarkMode: (dark: boolean) => void }) {
  return <AppShell darkMode={darkMode} setDarkMode={setDarkMode} />;
}
