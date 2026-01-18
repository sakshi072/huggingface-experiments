import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

interface Modal {
  id: string;
  type: 'confirmation' | 'edit-title' | 'info';
  data?: any;
}

interface UIState {
  // Modal management
  activeModals: Modal[];
  
  // Sidebar
  isSidebarOpen: boolean;
  
  // Notifications/Toasts
  notifications: Array<{
    id: string;
    message: string;
    type: 'success' | 'error' | 'info' | 'warning';
    timestamp: number;
  }>;
  
  // Actions
  openModal: (modal: Modal) => void;
  closeModal: (id: string) => void;
  closeAllModals: () => void;
  
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  
  addNotification: (message: string, type: 'success' | 'error' | 'info' | 'warning') => void;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    (set) => ({
      // Initial state
      activeModals: [],
      isSidebarOpen: true,
      notifications: [],
      
      // Modal actions
      openModal: (modal) => set((state) => ({
        activeModals: [...state.activeModals, modal]
      })),
      
      closeModal: (id) => set((state) => ({
        activeModals: state.activeModals.filter(m => m.id !== id)
      })),
      
      closeAllModals: () => set({ activeModals: [] }),
      
      // Sidebar actions
      toggleSidebar: () => set((state) => ({
        isSidebarOpen: !state.isSidebarOpen
      })),
      
      setSidebarOpen: (open) => set({ isSidebarOpen: open }),
      
      // Notification actions
      addNotification: (message, type) => set((state) => ({
        notifications: [
          ...state.notifications,
          {
            id: `${Date.now()}-${Math.random()}`,
            message,
            type,
            timestamp: Date.now(),
          }
        ]
      })),
      
      removeNotification: (id) => set((state) => ({
        notifications: state.notifications.filter(n => n.id !== id)
      })),
      
      clearNotifications: () => set({ notifications: [] }),
    }),
    { name: 'UIStore' }
  )
);