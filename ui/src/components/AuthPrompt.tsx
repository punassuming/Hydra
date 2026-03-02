import { Modal, Input, Typography, Space, message, Segmented } from "antd";
import { useEffect, useState } from "react";
import { setTokenForDomain, setTokenPreference, validateAdminToken, validateDomainToken } from "../api/client";
import { useActiveDomain } from "../context/ActiveDomainContext";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function AuthPrompt({ open, onClose, onSuccess }: Props) {
  const [token, setToken] = useState("");
  const [domainInput, setDomainInput] = useState("");
  const [mode, setMode] = useState<"domain" | "admin">("domain");
  const { domain, setDomain } = useActiveDomain();

  useEffect(() => {
    if (!open) return;
    setDomainInput(domain || "prod");
    setToken("");
    setMode("domain");
  }, [open, domain]);

  return (
    <Modal
      open={open}
      title="Sign In"
      closable={false}
      maskClosable={false}
      keyboard={false}
      onCancel={onClose}
      onOk={async () => {
        const finalToken = token.trim();
        const finalDomain = domainInput.trim();
        if (!finalToken) {
          message.error("Token required");
          return;
        }
        if (mode === "domain" && !finalDomain) {
          message.error("Domain required");
          return;
        }
        try {
          if (mode === "admin") {
            await validateAdminToken(finalToken);
            setTokenForDomain("admin", finalToken);
            setTokenPreference("admin");
            setDomain("admin");
            message.success("Admin token saved");
          } else {
            await validateDomainToken(finalDomain, finalToken);
            setTokenForDomain(finalDomain, finalToken);
            setTokenPreference("domain");
            setDomain(finalDomain);
            message.success(`Token saved for domain ${finalDomain}`);
          }
        } catch (err) {
          message.error(err instanceof Error ? err.message : "Authentication failed");
          return;
        }
        onSuccess?.();
        onClose();
      }}
      cancelButtonProps={{ style: { display: "none" } }}
      okText="Authenticate"
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        <Typography.Text>Choose login type, then enter the matching token.</Typography.Text>
        <Segmented
          block
          value={mode}
          options={[
            { label: "Domain Token", value: "domain" },
            { label: "Admin Token", value: "admin" },
          ]}
          onChange={(value) => setMode(value as "domain" | "admin")}
        />
        {mode === "domain" && (
          <Input value={domainInput} onChange={(e) => setDomainInput(e.target.value)} placeholder="Domain (e.g. prod)" />
        )}
        <Input.Password value={token} onChange={(e) => setToken(e.target.value)} placeholder="Token" />
        {mode === "admin" && (
          <Typography.Text type="secondary">
            Admin login is global. Use Settings or Admin page to switch domains after login.
          </Typography.Text>
        )}
      </Space>
    </Modal>
  );
}
