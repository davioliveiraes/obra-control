import { vi } from "vitest";
import type { AccessibleOrganization } from "../features/organizations/api";

export const firstOrganization: AccessibleOrganization = {
  id: 11,
  name: "Organização Alfa de teste",
  role: "owner",
};
export const secondOrganization: AccessibleOrganization = {
  id: 22,
  name: "Organização Beta de teste",
  role: "member",
};
export const noOrganization = { detail: "Nenhuma organização selecionada." };

export class TestChannel extends EventTarget {
  static instances: TestChannel[] = [];
  readonly name: string;
  closed = false;
  constructor(name: string) {
    super();
    this.name = name;
    TestChannel.instances.push(this);
  }
  postMessage = vi.fn((data: unknown) => {
    for (const peer of TestChannel.instances) {
      if (peer !== this && !peer.closed && peer.name === this.name)
        queueMicrotask(() => peer.emit(data));
    }
  });
  emit(data: unknown) {
    if (!this.closed) this.dispatchEvent(new MessageEvent("message", { data }));
  }
  close = vi.fn(() => {
    this.closed = true;
  });
}
