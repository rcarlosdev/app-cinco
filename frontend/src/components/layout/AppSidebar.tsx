// src/components/layout/AppSidebar.tsx
"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useSidebar } from "../../context/SidebarContext";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { House } from "lucide-react";
import { ChevronDownIcon, HorizontaLDots } from "../../icons/index";
import { IconMessageChatbot } from '@tabler/icons-react';
import { useAuthStore } from "@/store/auth.store";
import { hasCertificadosPermission } from "@/utils/permission";

type NavItem = {
  name: string;
  icon?: React.ReactNode;
  path?: string;
  requiresSuperuser?: boolean;
  subItems?: {
    name: string;
    path: string;
    new?: boolean;
    requiresSuperuser?: boolean;
  }[];
};

const defaultNavItems: NavItem[] = [
  {
    name: "Operaciones",
    subItems: [
      {
        name: "Gestion de Actividades",
        path: "/operaciones/gestion-actividades",
      },
    ],
  },
  {
    name: "RRHH",
    subItems: [
      {
        name: "Certificados Laborales",
        path: "/rrhh/certificados-laborales",
      },
    ],
  },
  {
    name: "Agente IA",
    icon: <IconMessageChatbot className="h-5 w-5" />,
    path: "/agente-ia",
    requiresSuperuser: true,
  },
  {
    name: "PROGRAMACION",
    subItems: [
      { name: "IA DEV", path: "/programacion/ia-dev", requiresSuperuser: true },
    ],
  },
];

const othersItems: NavItem[] = [];

const AppSidebar: React.FC = () => {
  const {
    isExpanded,
    isMobileOpen,
    collapseSidebar,
    closeMobileSidebar,
    expandSidebar,
  } = useSidebar();
  const pathname = usePathname();
  const user = useAuthStore((state) => state.user);
  const isSuperuser = Boolean(user?.is_superuser);
  const canAccessCertificados = useMemo(
    () => hasCertificadosPermission(user),
    [user],
  );

  const navItems = useMemo(
    () =>
      defaultNavItems.reduce<NavItem[]>((allowedItems, nav) => {
        if (nav.name === "RRHH" && !canAccessCertificados) {
          return allowedItems;
        }

        if (nav.requiresSuperuser && !isSuperuser) {
          return allowedItems;
        }

        const allowedSubItems = nav.subItems?.filter((subItem) => {
          if (subItem.path === "/rrhh/certificados-laborales") {
            return canAccessCertificados;
          }
          return !subItem.requiresSuperuser || isSuperuser;
        });

        if (nav.subItems && (!allowedSubItems || allowedSubItems.length === 0)) {
          return allowedItems;
        }

        allowedItems.push({
          ...nav,
          subItems: allowedSubItems,
        });
        return allowedItems;
      }, []),
    [isSuperuser, canAccessCertificados],
  );
  const isSidebarOpen = isExpanded || isMobileOpen;
  const asideRef = useRef<HTMLElement | null>(null);

  const [openSubmenu, setOpenSubmenu] = useState<{
    type: "main" | "others";
    index: number;
  } | null>(null);
  const [subMenuHeight, setSubMenuHeight] = useState<Record<string, number>>(
    {},
  );
  const [collapsedPreview, setCollapsedPreview] = useState<{
    key: string;
    left: number;
    top: number;
    prefix: string;
    name: string;
    isActive: boolean;
    icon?: React.ReactNode;
    useHomeIcon: boolean;
    forceActiveText: boolean;
  } | null>(null);
  const subMenuRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const isActive = (path: string) => path === pathname;

  const handleCollapsedItemMouseEnter = (
    event: React.MouseEvent<HTMLElement>,
    key: string,
    itemName: string,
    isItemActive: boolean,
    options?: {
      icon?: React.ReactNode;
      useHomeIcon?: boolean;
      forceActiveText?: boolean;
    },
  ) => {
    if (isSidebarOpen) return;

    const asideRect = asideRef.current?.getBoundingClientRect();
    if (!asideRect) return;

    const itemRect = event.currentTarget.getBoundingClientRect();
    setCollapsedPreview({
      key,
      left: itemRect.left - asideRect.left,
      top: itemRect.top - asideRect.top + itemRect.height / 2,
      prefix: itemName.substring(0, 2).toUpperCase(),
      name: itemName,
      isActive: isItemActive,
      icon: options?.icon,
      useHomeIcon: options?.useHomeIcon ?? false,
      forceActiveText: options?.forceActiveText ?? false,
    });
  };

  const handleCollapsedItemMouseLeave = (key: string) => {
    setCollapsedPreview((prev) => (prev?.key === key ? null : prev));
  };

  const renderMenuItems = (
    items: NavItem[],
    menuType: "main" | "others",
  ) => (
    <ul className="flex flex-col gap-4">
      {items.map((nav, index) => {
        const collapsedItemKey = `${menuType}-${index}`;
        const collapsedItemPrefix = nav.name.substring(0, 2).toUpperCase();
        const isItemActive = nav.subItems
          ? openSubmenu?.type === menuType && openSubmenu?.index === index
          : nav.path
            ? isActive(nav.path)
            : false;
        const itemClassName = isItemActive
          ? "menu-item-active"
          : "menu-item-inactive";
        const itemIconClassName = isItemActive
          ? "menu-item-icon-active"
          : "menu-item-icon-inactive";

        return (
          <li key={nav.name} className="relative">
            {nav.subItems ? (
              <button
                onClick={() => handleSubmenuToggle(index, menuType)}
                onMouseEnter={(event) =>
                  handleCollapsedItemMouseEnter(
                    event,
                    collapsedItemKey,
                    nav.name,
                    isItemActive,
                    { icon: nav.icon },
                  )
                }
                onMouseLeave={() => handleCollapsedItemMouseLeave(collapsedItemKey)}
                className={`menu-item group ${itemClassName} cursor-pointer ${!isSidebarOpen ? "lg:justify-center" : "lg:justify-start"
                  }`}
              >
                <span className={itemIconClassName}>
                  {nav.icon || collapsedItemPrefix}
                </span>
                {isSidebarOpen && <span className="menu-item-text">{nav.name}</span>}
                {isSidebarOpen && (
                  <ChevronDownIcon
                    className={`ml-auto h-5 w-5 transition-transform duration-200 ${isItemActive ? "text-brand-500 rotate-180" : ""
                      }`}
                  />
                )}
              </button>
            ) : (
              nav.path && (
                <Link
                  href={nav.path}
                  onMouseEnter={(event) =>
                    handleCollapsedItemMouseEnter(
                      event,
                      collapsedItemKey,
                      nav.name,
                      isItemActive,
                      { icon: nav.icon },
                    )
                  }
                  onMouseLeave={() => handleCollapsedItemMouseLeave(collapsedItemKey)}
                  className={`menu-item group ${itemClassName}`}
                >
                  <span className={itemIconClassName}>
                    {nav.icon || collapsedItemPrefix}
                  </span>
                  {isSidebarOpen && <span className="menu-item-text">{nav.name}</span>}
                </Link>
              )
            )}

            {nav.subItems && isSidebarOpen && (
              <div
                ref={(el) => {
                  subMenuRefs.current[`${menuType}-${index}`] = el;
                }}
                className="overflow-hidden transition-all duration-300"
                style={{
                  height:
                    openSubmenu?.type === menuType &&
                      openSubmenu?.index === index
                      ? `${subMenuHeight[`${menuType}-${index}`]}px`
                      : "0px",
                }}
              >
                <ul className="mt-2 ml-9 space-y-1">
                  {nav.subItems.map((subItem) => (
                    <li key={subItem.name}>
                      <Link
                        href={subItem.path}
                        className={`menu-dropdown-item ${isActive(subItem.path)
                            ? "menu-dropdown-item-active"
                            : "menu-dropdown-item-inactive"
                          }`}
                      >
                        {subItem.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );

  useEffect(() => {
    collapseSidebar();
    closeMobileSidebar();

    let matchedSubmenu: { type: "main" | "others"; index: number } | null =
      null;

    ["main", "others"].forEach((menuType) => {
      const items = menuType === "main" ? navItems : othersItems;
      items.forEach((nav, index) => {
        if (nav.subItems) {
          nav.subItems.forEach((subItem) => {
            if (subItem.path === pathname) {
              matchedSubmenu = {
                type: menuType as "main" | "others",
                index,
              };
            }
          });
        }
      });
    });

    // Sync submenu open state with current route.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpenSubmenu(matchedSubmenu);
  }, [pathname, navItems, collapseSidebar, closeMobileSidebar]);

  useEffect(() => {
    if (openSubmenu !== null) {
      const key = `${openSubmenu.type}-${openSubmenu.index}`;
      if (subMenuRefs.current[key]) {
        setSubMenuHeight((prevHeights) => ({
          ...prevHeights,
          [key]: subMenuRefs.current[key]?.scrollHeight || 0,
        }));
      }
    }
  }, [openSubmenu]);

  const handleSubmenuToggle = (index: number, menuType: "main" | "others") => {
    if (!isSidebarOpen) {
      setCollapsedPreview(null);
      expandSidebar();
      setOpenSubmenu({ type: menuType, index });
      return;
    }

    setOpenSubmenu((prevOpenSubmenu) => {
      if (
        prevOpenSubmenu &&
        prevOpenSubmenu.type === menuType &&
        prevOpenSubmenu.index === index
      ) {
        return null;
      }
      return { type: menuType, index };
    });
  };

  return (
    <aside
      ref={asideRef}
      className={`fixed top-0 left-0 z-100000 mt-16 flex h-screen flex-col border-r border-gray-200 bg-white px-5 text-gray-900 transition-all duration-300 ease-in-out lg:mt-0 dark:border-gray-800 dark:bg-gray-900 ${isSidebarOpen ? "w-72.5" : "w-22.5"
        } ${isMobileOpen ? "translate-x-0" : "-translate-x-full"} lg:translate-x-0`}
      onMouseLeave={() => setCollapsedPreview(null)}
    >
      <div
        className={`flex items-center py-8 ${!isSidebarOpen ? "lg:justify-center" : "justify-start"
          }`}
      >
        <Link
          href="/"
          onMouseEnter={(event) =>
            handleCollapsedItemMouseEnter(event, "logo-home", "Inicio", isActive("/"), {
              useHomeIcon: true,
              forceActiveText: true,
            })
          }
          onMouseLeave={() => handleCollapsedItemMouseLeave("logo-home")}
          onClick={() => setCollapsedPreview(null)}
          className={`relative block h-10 overflow-hidden transition-[width] duration-300 ease-in-out ${isSidebarOpen ? "w-[150px]" : "w-8"
            }`}
        >
          <Image
            src="/images/logo/logo-cinco.svg"
            alt="Logo expandido"
            width={150}
            height={40}
            priority
            className={`absolute top-1/2 left-0 h-10 w-[150px] max-w-none -translate-y-1/2 transition-opacity duration-200 ${isSidebarOpen ? "opacity-100" : "opacity-0"
              }`}
          />
          <Image
            src="/images/logo/logo-cinco.svg"
            alt="Logo contraido"
            width={32}
            height={32}
            priority
            className={`absolute top-1/2 left-0 h-8 w-8 -translate-y-1/2 transition-opacity duration-200 ${isSidebarOpen ? "opacity-0" : "opacity-100"
              }`}
          />
        </Link>
      </div>

      <div className="no-scrollbar flex flex-col overflow-y-auto duration-300 ease-linear">
        <nav className="mb-6">
          <div className="flex flex-col gap-4">
            <div>
              <h2
                className={`mb-4 flex text-xs leading-5 text-gray-400 uppercase ${!isSidebarOpen ? "lg:justify-center" : "justify-start"
                  }`}
              >
                {isSidebarOpen ? "Menu" : <HorizontaLDots />}
              </h2>
              {renderMenuItems(navItems, "main")}
            </div>

            {othersItems.length > 0 && (
              <div>
                <h2
                  className={`mb-4 flex text-xs leading-5 text-gray-400 uppercase ${!isSidebarOpen ? "lg:justify-center" : "justify-start"
                    }`}
                >
                  {isSidebarOpen ? "Others" : <HorizontaLDots />}
                </h2>
                {renderMenuItems(othersItems, "others")}
              </div>
            )}
          </div>
        </nav>
      </div>

      {!isSidebarOpen && collapsedPreview && (
        <div
          className="pointer-events-none absolute z-70"
          style={{
            left: collapsedPreview.left,
            top: collapsedPreview.top,
            transform: "translateY(-50%)",
          }}
        >
          <div
            className={`menu-item w-fit! bg-gray-50/95 backdrop-blur-sm dark:bg-gray-800/95 ${collapsedPreview.isActive
                ? "menu-item-active"
                : "menu-item-inactive"
              } shadow-theme-sm`}
          >
            <span
              className={`${collapsedPreview.isActive
                  ? "menu-item-icon-active"
                  : "menu-item-icon-inactive"
                }`}
            >
              {collapsedPreview.useHomeIcon ? (
                <House className="h-4 w-4" />
              ) : collapsedPreview.icon ? (
                collapsedPreview.icon
              ) : (
                collapsedPreview.prefix
              )}
            </span>
            <span
              className={`menu-item-text ${collapsedPreview.forceActiveText
                  ? "text-brand-500! dark:text-brand-400!"
                  : ""
                }`}
            >
              {collapsedPreview.name}
            </span>
          </div>
        </div>
      )}
    </aside>
  );
};

export default AppSidebar;
