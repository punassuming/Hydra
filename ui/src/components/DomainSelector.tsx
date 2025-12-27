import { Select, Space, Typography, Button, Modal, Input, Tag } from "antd";
import { useState } from "react";
import { setActiveDomain as storeDomain, setTokenForDomain, forgetToken, getAdminToken, hasTokenForDomain } from "../api/client";
import { useDomains } from "../hooks/useDomains";
import { useActiveDomain } from "../context/ActiveDomainContext";

export function DomainSelector({ onChange }: { onChange?: (domain: string) => void }) {
  const domainOptions = useDomains();
  const { domain: current, setDomain } = useActiveDomain();
  const [switchModal, setSwitchModal] = useState<{ open: boolean; domain?: string; token?: string }>({ open: false });
  const adminToken = getAdminToken();

  return (
    <Space>
      <Space direction="vertical" size={0}>
        <Typography.Text style={{ color: "#cbd5f5" }}>Active Domain</Typography.Text>
        <Tag color={hasTokenForDomain(current) ? "green" : "volcano"} style={{ marginTop: 2 }}>
          {hasTokenForDomain(current) ? "Token saved" : "No token"}
        </Tag>
      </Space>
      <Select
        size="small"
        value={current}
        options={domainOptions.map((o) => ({ label: o.label, value: o.domain }))}
        onChange={(domain) => {
          storeDomain(domain);
          setDomain(domain);
          onChange?.(domain);
        }}
        style={{ minWidth: 140 }}
      />
      <Button size="small" onClick={() => setSwitchModal({ open: true, domain: current })}>
        Switch Token
      </Button>
      {adminToken && (
        <Button
          size="small"
          onClick={() => {
            setTokenForDomain(current, adminToken);
            storeDomain(current);
            setDomain(current);
          }}
        >
          Use Admin
        </Button>
      )}
      <Typography.Link
        onClick={() => {
          forgetToken(current);
        }}
      >
        Forget Token
      </Typography.Link>
      <Modal
        open={switchModal.open}
        title={`Set token for ${switchModal.domain}`}
        onCancel={() => setSwitchModal({ open: false })}
        onOk={() => {
          if (switchModal.domain && switchModal.token) {
            setTokenForDomain(switchModal.domain, switchModal.token);
            storeDomain(switchModal.domain);
            setDomain(switchModal.domain);
            setSwitchModal({ open: false });
          }
        }}
      >
        <Input
          placeholder="Token"
          value={switchModal.token}
          onChange={(e) => setSwitchModal((prev) => ({ ...prev, token: e.target.value }))}
        />
      </Modal>
    </Space>
  );
}
