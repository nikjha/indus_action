import { configureStore, createSlice, PayloadAction } from "@reduxjs/toolkit";
import { api } from "./api";

type AuthState = { token: string; role: string; username: string };
const initialAuth: AuthState = {
  token: localStorage.getItem("token") || "",
  role: localStorage.getItem("role") || "",
  username: localStorage.getItem("username") || "",
};

const authSlice = createSlice({
  name: "auth",
  initialState: initialAuth,
  reducers: {
    setAuth: (state, action: PayloadAction<AuthState>) => {
      state.token = action.payload.token;
      state.role = action.payload.role;
      state.username = action.payload.username;
      localStorage.setItem("token", state.token);
      localStorage.setItem("role", state.role);
      localStorage.setItem("username", state.username);
    },
    clearAuth: (state) => {
      state.token = "";
      state.role = "";
      state.username = "";
      localStorage.removeItem("token");
      localStorage.removeItem("role");
      localStorage.removeItem("username");
    },
  },
});

export const { setAuth, clearAuth } = authSlice.actions;

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    auth: authSlice.reducer,
  },
  middleware: (gDM) => gDM().concat(api.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
