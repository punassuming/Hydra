import { useEffect, useState } from "react";
import { Button, Checkbox, Divider, Drawer, Input, Select, Space, Switch, Tag, Typography, message } from "antd";
import { SettingOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { forgetToken, getAdminToken, hasTokenForDomain, setTokenForDomain } from "../api/client";
import { useDomains } from "../hooks/useDomains";
import { useActiveDomain } from "../context/ActiveDomainContext";

type Props = {
  darkMode: boolean;
  setDarkMode: (next: boolean) => void;
};

export function HeaderSettings({ darkMode, setDarkMode }: Props) {
  const navigate = useNavigate();
  const domainOptions = useDomains();
  const { domain: currentDomain, setDomain } = useActiveDomain();
  const [open, setOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [saveAsAdmin, setSaveAsAdmin] = useState(false);
  const adminToken = getAdminToken();
  const availableDomains = domainOptions.map((o) => o.domain);

  useEffect(() => {
    if (!availableDomains.length || availableDomains.includes(currentDomain)) {
      return;
    }
    const fallback = availableDomains.includes("prod") ? "prod" : availableDomains[0];
    setDomain(fallback);
  }, [availableDomains, currentDomain, setDomain]);

  const saveToken = () => {
    const token = tokenInput.trim();
    if (!token) {
      message.error("Token required");
      return;
    }
    if (saveAsAdmin) {
      setTokenForDomain("admin", token);
      message.success("Admin token saved");
    } else {
      setTokenForDomain(currentDomain, token);
      message.success(`Token saved for domain ${currentDomain}`);
    }
    setTokenInput("");
  };

  return (
    <>
      <Button icon={<SettingOutlined />} onClick={() => setOpen(true)}>
        Settings
      </Button>
      <Drawer
        title="Workspace Settings"
        open={open}
        onClose={() => setOpen(false)}
        width={420}
        destroyOnHidden
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <Space direction="vertical" size={4}>
            <Typography.Text strong>Active domain</Typography.Text>
            <Select
              value={currentDomain}
              options={domainOptions.map((o) => ({ label: o.label, value: o.domain }))}
              onChange={(domain) => setDomain(domain)}
            />
            <Tag color={hasTokenForDomain(currentDomain) ? "green" : "volcano"}>
              {hasTokenForDomain(currentDomain) ? "Domain token saved" : "No domain token saved"}
            </Tag>
          </Space>

          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Typography.Text strong>Token management</Typography.Text>
            <Checkbox checked={saveAsAdmin} onChange={(e) => setSaveAsAdmin(e.target.checked)}>
              Save entered token as admin token
            </Checkbox>
            <Input.Password
              value={tokenInput}
              placeholder={saveAsAdmin ? "Admin token" : `Token for ${currentDomain}`}
              onChange={(e) => setTokenInput(e.target.value)}
            />
            <Space wrap>
              <Button type="primary" onClick={saveToken}>
                Save Token
              </Button>
              <Button
                onClick={() => {
                  if (!adminToken) {
                    message.error("No saved admin token");
                    return;
                  }
                  setTokenForDomain(currentDomain, adminToken);
                  message.success(`Applied admin token to ${currentDomain}`);
                }}
              >
                Use Admin Token
              </Button>
              <Button
                onClick={() => {
                  forgetToken(currentDomain);
                  message.success(`Forgot token for ${currentDomain}`);
                }}
              >
                Forget Domain Token
              </Button>
            </Space>
          </Space>

          <Divider style={{ margin: "8px 0" }} />

          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Typography.Text strong>Appearance</Typography.Text>
            <Space>
              <Typography.Text>{darkMode ? "Dark mode" : "Light mode"}</Typography.Text>
              <Switch checked={darkMode} onChange={setDarkMode} />
            </Space>
          </Space>

          <Divider style={{ margin: "8px 0" }} />

          <Button
            onClick={() => {
              setOpen(false);
              navigate("/admin");
            }}
          >
            Open Admin Workspace
          </Button>
        </Space>
      </Drawer>
    </>
  );
}
