"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  UserProfile,
  UserRole,
  apiLogin,
  apiRegister,
  apiGetMe,
  apiLogout,
  apiBootstrapOrganization,
} from "./api";

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string, orgSlugOrId: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    fullName: string,
    orgSlugOrId: string
  ) => Promise<void>;
  bootstrap: (
    orgName: string,
    orgSlug: string,
    adminEmail: string,
    adminPassword: string,
    adminFullName: string
  ) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = "brandguard_token";

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  // Load session on mount
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      setIsLoading(false);
      return;
    }

    setToken(storedToken);
    apiGetMe()
      .then((profile) => {
        setUser(profile);
      })
      .catch((err) => {
        console.warn("Session expired or invalid:", err);
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  const login = useCallback(
    async (email: string, password: string, orgSlugOrId: string) => {
      setIsLoading(true);
      try {
        const isUUID =
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
            orgSlugOrId.trim()
          );

        const res = await apiLogin({
          email: email.trim(),
          password,
          ...(isUUID
            ? { organization_id: orgSlugOrId.trim() }
            : { organization_slug: orgSlugOrId.trim().toLowerCase() }),
        });

        localStorage.setItem(TOKEN_KEY, res.access_token);
        setToken(res.access_token);
        setUser(res.user);
        router.push("/");
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const bootstrap = useCallback(
    async (
      orgName: string,
      orgSlug: string,
      adminEmail: string,
      adminPassword: string,
      adminFullName: string
    ) => {
      setIsLoading(true);
      try {
        const res = await apiBootstrapOrganization({
          org_name: orgName.trim(),
          org_slug: orgSlug.trim().toLowerCase(),
          admin_email: adminEmail.trim(),
          admin_password: adminPassword,
          admin_full_name: adminFullName.trim(),
        });

        localStorage.setItem(TOKEN_KEY, res.access_token);
        setToken(res.access_token);
        setUser(res.user);
        router.push("/");
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const register = useCallback(
    async (
      email: string,
      password: string,
      fullName: string,
      orgSlugOrId: string
    ) => {
      setIsLoading(true);
      try {
        const isUUID =
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
            orgSlugOrId.trim()
          );

        await apiRegister({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          ...(isUUID
            ? { organization_id: orgSlugOrId.trim() }
            : { organization_slug: orgSlugOrId.trim().toLowerCase() }),
        });

        // After successful registration, log in
        await login(email, password, orgSlugOrId);
      } finally {
        setIsLoading(false);
      }
    },
    [login]
  );

  const logout = useCallback(async () => {
    try {
      if (token) {
        await apiLogout();
      }
    } catch (e) {
      console.warn("Logout error:", e);
    } finally {
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
      router.push("/login");
    }
  }, [token, router]);

  const hasPermission = useCallback(
    (permission: string): boolean => {
      if (!user) return false;
      if (user.role === "ADMIN") return true;
      return user.permissions?.includes(permission) ?? false;
    },
    [user]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user && !!token,
        login,
        register,
        bootstrap,
        logout,
        hasPermission,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
