import { ChevronDown, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { Dropdown, DropdownItem, DropdownLabel, DropdownSeparator } from "@/components/ui/Dropdown";

/**
 * Light/dark switch. A plain button flips the theme; the menu underneath also
 * offers "Match system", which is a distinct state from either fixed choice —
 * it keeps following the OS instead of pinning a value.
 */
export function ThemeToggle() {
  const { theme, setTheme, toggle, followsSystem, clearPreference } = useTheme();
  return (
    <div className="flex items-center">
      <button
        onClick={toggle}
        title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        className="flex h-8 w-8 items-center justify-center rounded-full text-content-2 transition-colors hover:bg-overlay-1 hover:text-content-1"
      >
        {theme === "dark" ? <Sun className="h-[1.1rem] w-[1.1rem]" /> : <Moon className="h-[1.1rem] w-[1.1rem]" />}
      </button>
      <Dropdown
        variant="ghost"
        align="right"
        width="w-48"
        title="Theme"
        label={<span className="sr-only">Theme options</span>}
        icon={<ChevronDown className="h-3 w-3" />}
        className="[&>button>svg:last-child]:hidden"
      >
        {(close) => (
          <>
            <DropdownLabel>Appearance</DropdownLabel>
            <DropdownItem
              icon={<Moon className="h-3.5 w-3.5" />}
              selected={!followsSystem && theme === "dark"}
              onSelect={() => {
                setTheme("dark");
                close();
              }}
            >
              Dark
            </DropdownItem>
            <DropdownItem
              icon={<Sun className="h-3.5 w-3.5" />}
              selected={!followsSystem && theme === "light"}
              onSelect={() => {
                setTheme("light");
                close();
              }}
            >
              Light
            </DropdownItem>
            <DropdownSeparator />
            <DropdownItem
              icon={<Monitor className="h-3.5 w-3.5" />}
              selected={followsSystem}
              hint={followsSystem ? theme : undefined}
              onSelect={() => {
                clearPreference();
                close();
              }}
            >
              Match system
            </DropdownItem>
          </>
        )}
      </Dropdown>
    </div>
  );
}
