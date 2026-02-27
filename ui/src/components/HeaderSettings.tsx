import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Checkbox, Divider, Drawer, Input, Modal, Select, Space, Tag, Typography, message } from "antd";
import { SettingOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { forgetToken, getAdminToken, hasTokenForDomain, setTokenForDomain } from "../api/client";
import { createDomain, rotateDomainToken } from "../api/admin";
import { useDomains } from "../hooks/useDomains";
import { useActiveDomain } from "../context/ActiveDomainContext";

export function HeaderSettings() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const domainOptions = useDomains();
  const { domain: currentDomain, setDomain } = useActiveDomain();
  const [open, setOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [saveAsAdmin, setSaveAsAdmin] = useState(false);
  const [adminDomain, setAdminDomain] = useState(currentDomain);
  const [newDomain, setNewDomain] = useState("");
  const [newDomainToken, setNewDomainToken] = useState("");
  const [tokenModal, setTokenModal] = useState<{ open: boolean; domain?: string; token?: string }>({ open: false });
  const adminToken = getAdminToken();
  const availableDomains = domainOptions.map((o) => o.domain);
  const effectiveDomainOptions = useMemo(
    () => (domainOptions.length ? domainOptions : [{ domain: currentDomain, label: currentDomain }]),
    [domainOptions, currentDomain],
  );

  useEffect(() => {
    if (!availableDomains.length || availableDomains.includes(currentDomain)) {
      return;
    }
    const fallback = availableDomains.includes("prod") ? "prod" : availableDomains[0];
    setDomain(fallback);
  }, [availableDomains, currentDomain, setDomain]);

  useEffect(() => {
    setAdminDomain(currentDomain);
  }, [currentDomain]);

  const rotateTokenMut = useMutation({
    mutationFn: (domain: string) => rotateDomainToken(domain),
    onSuccess: (data) => {
      setTokenForDomain(data.domain, data.token);
      setDomain(data.domain);
      setTokenModal({ open: true, domain: data.domain, token: data.token });
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      message.success(`Rotated token for ${data.domain}`);
    },
    onError: (err: Error) => message.error(err.message),
  });

  const createDomainMut = useMutation({
    mutationFn: ({ domain, token }: { domain: string; token?: string }) => createDomain({ domain, token }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      if (data.token) {
        setTokenForDomain(data.domain, data.token);
        setTokenModal({ open: true, domain: data.domain, token: data.token });
      }
      setDomain(data.domain);
      setAdminDomain(data.domain);
      setNewDomain("");
      setNewDomainToken("");
      message.success(`Created domain ${data.domain}`);
    },
    onError: (err: Error) => message.error(err.message),
  });

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
          <Typography.Text type="secondary">
            Worker auth key is a pair: <Typography.Text code>domain + token</Typography.Text>. Do not use a single{" "}
            <Typography.Text code>domain:token</Typography.Text> string.
          </Typography.Text>
          <Space direction="vertical" size={4}>
            <Typography.Text strong>Active domain</Typography.Text>
            {adminToken ? (
              <Select
                value={currentDomain}
                options={effectiveDomainOptions.map((o) => ({ label: o.label, value: o.domain }))}
                onChange={(domain) => setDomain(domain)}
              />
            ) : (
              <Typography.Text>{currentDomain}</Typography.Text>
            )}
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

          {adminToken && (
            <>
              <Divider style={{ margin: "8px 0" }} />
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Typography.Text strong>Domain admin</Typography.Text>
                <Select
                  value={adminDomain}
                  options={effectiveDomainOptions.map((o) => ({ label: o.label, value: o.domain }))}
                  onChange={(domain) => setAdminDomain(domain)}
                />
                <Space wrap>
                  <Button
                    onClick={() => {
                      setTokenForDomain(adminDomain, adminToken);
                      setDomain(adminDomain);
                      message.success(`Using admin token in domain ${adminDomain}`);
                    }}
                  >
                    Use Admin In Domain
                  </Button>
                  <Button
                    loading={rotateTokenMut.isPending}
                    onClick={() => rotateTokenMut.mutate(adminDomain)}
                  >
                    Rotate Domain Token
                  </Button>
                </Space>
                <Typography.Text type="secondary">
                  Create a new domain quickly from Settings.
                </Typography.Text>
                <Input
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  placeholder="New domain name"
                />
                <Input.Password
                  value={newDomainToken}
                  onChange={(e) => setNewDomainToken(e.target.value)}
                  placeholder="Optional token (leave blank to auto-generate)"
                />
                <Button
                  loading={createDomainMut.isPending}
                  onClick={() => {
                    const domain = newDomain.trim();
                    if (!domain) {
                      message.error("Domain name required");
                      return;
                    }
                    createDomainMut.mutate({
                      domain,
                      token: newDomainToken.trim() || undefined,
                    });
                  }}
                >
                  Create Domain
                </Button>
              </Space>
            </>
          )}

          <Divider style={{ margin: "8px 0" }} />

          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Typography.Text strong>Quick actions</Typography.Text>
            <Space wrap>
              <Button onClick={() => { setOpen(false); navigate("/"); }}>Jobs</Button>
              <Button onClick={() => { setOpen(false); navigate("/workers"); }}>Workers</Button>
              <Button onClick={() => { setOpen(false); navigate("/status"); }}>Status</Button>
              <Button onClick={() => { setOpen(false); navigate("/admin"); }}>Admin</Button>
            </Space>
            <Button
              danger
              onClick={() => {
                forgetToken();
                setOpen(false);
              }}
            >
              Sign Out (All Tokens)
            </Button>
          </Space>
        </Space>
      </Drawer>
      <Modal
        open={tokenModal.open}
        footer={null}
        onCancel={() => setTokenModal({ open: false })}
        title={`Domain Token${tokenModal.domain ? ` - ${tokenModal.domain}` : ""}`}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text strong>Copy this token for UI login and workers. It will not be shown again.</Typography.Text>
          <Input.Password
            readOnly
            value={tokenModal.token ?? ""}
            style={{ fontFamily: "monospace" }}
          />
          <Button onClick={() => { navigator.clipboard.writeText(tokenModal.token ?? ""); message.success("Token copied to clipboard"); }}>
            Copy Token
          </Button>
          <Typography.Text type="secondary">Worker start example:</Typography.Text>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
{`WORKER_DOMAIN=${tokenModal.domain ?? currentDomain} API_TOKEN=<domain_token> \\
docker compose -f docker-compose.worker.yml up --build`}
            </pre>
          </Typography.Paragraph>
        </Space>
      </Modal>
    </>
  );
}
