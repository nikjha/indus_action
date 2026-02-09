import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

const BASE = (window as any).GATEWAY_BASE || "http://localhost:8000";

export const api = createApi({
  reducerPath: "api",
  baseQuery: fetchBaseQuery({
    baseUrl: BASE,
    prepareHeaders: (headers) => {
      const token = localStorage.getItem("token");
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return headers;
    },
  }),
  endpoints: (builder) => ({
    login: builder.mutation<{ access_token: string; role: string; user: { username: string } }, { username: string; password: string }>({
      query: (body) => ({ url: "/login", method: "POST", body }),
    }),
    createTask: builder.mutation<any, any>({
      query: (body) => ({ url: "/tasks", method: "POST", body }),
    }),
    eligibleUsers: builder.query<any, number>({
      query: (taskId) => ({ url: `/tasks/${taskId}/eligible-users` }),
    }),
    myEligibleTasks: builder.query<any, number>({
      query: (userId) => ({ url: `/my-eligible-tasks?user_id=${userId}` }),
    }),
    recompute: builder.mutation<any, any>({
      query: (body) => ({ url: "/tasks/recompute-eligibility", method: "POST", body }),
    }),
    listUsers: builder.query<any, void>({
      query: () => ({ url: "/users" }),
    }),
    createUser: builder.mutation<any, any>({
      query: (body) => ({ url: "/users", method: "POST", body }),
    }),
    updateUser: builder.mutation<any, { id: number } & any>({
      query: ({ id, ...body }) => ({ url: `/users/${id}`, method: "PATCH", body }),
    }),
    deleteUser: builder.mutation<any, number>({
      query: (id) => ({ url: `/users/${id}`, method: "DELETE" }),
    }),
    listTasks: builder.query<any, void>({
      query: () => ({ url: "/tasks" }),
    }),
    getTask: builder.query<any, number>({
      query: (id) => ({ url: `/tasks/${id}` }),
    }),
    updateTask: builder.mutation<any, { id: number; title?: string; description?: string; status?: string; priority?: number; due_date?: string; rules?: any }>({
      query: ({ id, ...body }) => ({ url: `/tasks/${id}`, method: "PATCH", body }),
    }),
    deleteTask: builder.mutation<any, number>({
      query: (id) => ({ url: `/tasks/${id}`, method: "DELETE" }),
    }),
    listAssignments: builder.query<any, void>({
      query: () => ({ url: "/assignments" }),
    }),
    getAssignment: builder.query<any, number>({
      query: (taskId) => ({ url: `/assignments/${taskId}` }),
    }),
    assignmentsByUser: builder.query<any, number>({
      query: (userId) => ({ url: `/assignments/user/${userId}` }),
    }),
    upsertAssignment: builder.mutation<any, { task_id: number; user_id: number; status?: string }>({
      query: (body) => ({ url: "/assignments", method: "POST", body }),
    }),
    updateAssignmentStatus: builder.mutation<any, { task_id: number; status: string }>({
      query: ({ task_id, status }) => ({ url: `/assignments/${task_id}/status`, method: "PATCH", body: { status } }),
    }),
    updateAssignmentStatusByUid: builder.mutation<any, { task_uid: string; status: string }>({
      query: ({ task_uid, status }) => ({ url: `/assignments/uid/${task_uid}/status`, method: "PATCH", body: { status } }),
    }),
  }),
});

export const {
  useLoginMutation,
  useCreateTaskMutation,
  useEligibleUsersQuery,
  useMyEligibleTasksQuery,
  useRecomputeMutation,
  useListUsersQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useListTasksQuery,
  useGetTaskQuery,
  useUpdateTaskMutation,
  useDeleteTaskMutation,
  useListAssignmentsQuery,
  useGetAssignmentQuery,
  useAssignmentsByUserQuery,
  useUpsertAssignmentMutation,
  useUpdateAssignmentStatusMutation,
  useUpdateAssignmentStatusByUidMutation,
} = api;
