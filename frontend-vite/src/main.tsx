import React from "react";
import ReactDOM from "react-dom/client";
import { Provider, useDispatch, useSelector } from "react-redux";
import { createBrowserRouter, RouterProvider, Link } from "react-router-dom";
import { store, setAuth, clearAuth } from "./store";
import {
  useLoginMutation,
  useCreateTaskMutation,
  useEligibleUsersQuery,
  useMyEligibleTasksQuery,
  useRecomputeMutation,
  useListUsersQuery,
  useCreateUserMutation,
  useListTasksQuery,
  useGetTaskQuery,
  useListAssignmentsQuery,
  useGetAssignmentQuery,
  useAssignmentsByUserQuery,
  useUpsertAssignmentMutation,
  useUpdateTaskMutation,
  useDeleteTaskMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
} from "./api";
import "./styles.css";

function Layout({ children }: { children: React.ReactNode }) {
  const dispatch = useDispatch();
  const auth = useSelector((s: any) => s.auth);
  return (
    <>
      <header>
        <h1>Indus Action Portal</h1>
        <nav>
          <Link to="/">Home</Link>
          <Link to="/tasks">Tasks</Link>
          <Link to="/eligible">Eligible</Link>
          <Link to="/my-tasks">My Tasks</Link>
          {auth.role === "ADMIN" ? (
            <>
              <Link to="/admin/create-task">Create Task</Link>
              <Link to="/admin/users">Users</Link>
              <Link to="/admin/recompute">Recompute</Link>
            </>
          ) : null}
        </nav>
        <div id="auth-status">
          <span id="user-info">
            {auth.token ? `Logged in as ${auth.username} (${auth.role})` : "Not logged in"}
          </span>
          {auth.token ? (
            <button className="secondary" onClick={() => dispatch(clearAuth())}>Logout</button>
          ) : null}
        </div>
      </header>
      <main>{children}</main>
      <footer><small>© Indus Action</small></footer>
    </>
  );
}

function LoginPage() {
  const dispatch = useDispatch();
  const [login, { isLoading }] = useLoginMutation();
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  async function onSubmit() {
    const res: any = await login({ username, password }).unwrap();
    dispatch(setAuth({ token: res.access_token, role: res.role, username: res.user.username }));
  }
  return (
    <Layout>
      <section>
        <h2>Login</h2>
        <div className="form-row"><label>Username</label><input value={username} onChange={(e)=>setUsername(e.target.value)} /></div>
        <div className="form-row"><label>Password</label><input type="password" value={password} onChange={(e)=>setPassword(e.target.value)} /></div>
        <button onClick={onSubmit} disabled={isLoading}>Login</button>
        <p className="hint">Admin role is granted if username starts with "admin".</p>
      </section>
    </Layout>
  );
}

function TasksPage() {
  const { data: list, refetch, isFetching } = useListTasksQuery();
  const [taskId, setTaskId] = React.useState("");
  const { data: task, refetch: refetchTask, isFetching: fetchingTask } = useGetTaskQuery(taskId ? Number(taskId) : 0, { skip: !taskId });
  return (
    <Layout>
      <section>
        <h2>Tasks</h2>
        <div className="grid">
          <div className="panel">
            <h3>List Tasks</h3>
            <button onClick={()=>refetch()} disabled={isFetching}>List Tasks</button>
            <pre className="result">{list ? JSON.stringify(list, null, 2) : ""}</pre>
          </div>
          <div className="panel">
            <h3>Task Details</h3>
            <div className="form-row"><label>Task ID</label><input value={taskId} onChange={(e)=>setTaskId(e.target.value)} type="number" /></div>
            <button onClick={()=>refetchTask()} disabled={!taskId || fetchingTask}>Get Task</button>
            <pre className="result">{task ? JSON.stringify(task, null, 2) : ""}</pre>
          </div>
        </div>
      </section>
    </Layout>
  );
}

function EligiblePage() {
  const [taskId, setTaskId] = React.useState("");
  const { data, refetch, isFetching } = useEligibleUsersQuery(taskId ? Number(taskId) : 0, { skip: !taskId });
  return (
    <Layout>
      <section>
        <h2>Eligible Users</h2>
        <div className="form-row"><label>Task ID</label><input value={taskId} onChange={(e)=>setTaskId(e.target.value)} type="number" /></div>
        <button onClick={()=>refetch()} disabled={!taskId || isFetching}>Fetch Eligible Users</button>
        <pre className="result">{data ? JSON.stringify(data, null, 2) : ""}</pre>
      </section>
    </Layout>
  );
}

function MyTasksPage() {
  const [userId, setUserId] = React.useState("");
  const { data, refetch, isFetching } = useMyEligibleTasksQuery(userId ? Number(userId) : 0, { skip: !userId });
  return (
    <Layout>
      <section>
        <h2>My Eligible Tasks</h2>
        <div className="form-row"><label>User ID</label><input value={userId} onChange={(e)=>setUserId(e.target.value)} type="number" /></div>
        <button onClick={()=>refetch()} disabled={!userId || isFetching}>Fetch My Tasks</button>
        <pre className="result">{data ? JSON.stringify(data, null, 2) : ""}</pre>
      </section>
    </Layout>
  );
}

function AdminCreateTaskPage() {
  const role = useSelector((s:any)=>s.auth.role);
  const [createTask, { isLoading }] = useCreateTaskMutation();
  const [updateTask] = useUpdateTaskMutation();
  const [deleteTask] = useDeleteTaskMutation();
  const [id, setId] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [department, setDepartment] = React.useState("");
  const [minExp, setMinExp] = React.useState("");
  const [maxActive, setMaxActive] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [priority, setPriority] = React.useState("");
  const [status, setStatus] = React.useState("TODO");
  const [dueDate, setDueDate] = React.useState("");
  const [result, setResult] = React.useState("");
  if (role !== "ADMIN") return <Layout><section><p>Admin only</p></section></Layout>;
  async function onSubmit() {
    const payload: any = {
      id: Number(id),
      title,
      ...(description ? { description } : {}),
      ...(priority ? { priority: Number(priority) } : {}),
      ...(status ? { status } : {}),
      ...(dueDate ? { due_date: dueDate } : {}),
      rules: {
        ...(department ? { department } : {}),
        ...(minExp ? { min_experience: Number(minExp) } : {}),
        ...(maxActive ? { max_active_tasks: Number(maxActive) } : {}),
      },
    };
    try {
      const res = await createTask(payload).unwrap();
      setResult(JSON.stringify(res, null, 2));
    } catch {
      setResult("Error creating task");
    }
  }
  async function onUpdate() {
    const body: any = {
      id: Number(id),
      ...(title ? { title } : {}),
      ...(description ? { description } : {}),
      ...(priority ? { priority: Number(priority) } : {}),
      ...(status ? { status } : {}),
      ...(dueDate ? { due_date: dueDate } : {}),
      rules: {
        ...(department ? { department } : {}),
        ...(minExp ? { min_experience: Number(minExp) } : {}),
        ...(maxActive ? { max_active_tasks: Number(maxActive) } : {}),
      },
    };
    try {
      const res = await updateTask(body).unwrap();
      setResult(JSON.stringify(res, null, 2));
    } catch {
      setResult("Error updating task");
    }
  }
  async function onDelete() {
    try {
      const res = await deleteTask(Number(id)).unwrap();
      setResult(JSON.stringify(res, null, 2));
    } catch {
      setResult("Error deleting task");
    }
  }
  return (
    <Layout>
      <section>
        <h2>Create Task (ADMIN)</h2>
        <div className="form-row"><label>Task ID</label><input value={id} onChange={(e)=>setId(e.target.value)} type="number" /></div>
        <div className="form-row"><label>Title</label><input value={title} onChange={(e)=>setTitle(e.target.value)} /></div>
        <div className="form-row"><label>Description</label><input value={description} onChange={(e)=>setDescription(e.target.value)} /></div>
        <div className="form-row"><label>Priority</label><input value={priority} onChange={(e)=>setPriority(e.target.value)} type="number" /></div>
        <div className="form-row"><label>Status</label>
          <select value={status} onChange={(e)=>setStatus(e.target.value)}>
            <option value="TODO">TODO</option>
            <option value="IN_PROGRESS">IN_PROGRESS</option>
            <option value="DONE">DONE</option>
            <option value="WAITING_FOR_ELIGIBLE_USER">WAITING_FOR_ELIGIBLE_USER</option>
          </select>
        </div>
        <div className="form-row"><label>Due Date</label><input value={dueDate} onChange={(e)=>setDueDate(e.target.value)} type="date" /></div>
        <div className="form-row"><label>Department</label><input value={department} onChange={(e)=>setDepartment(e.target.value)} /></div>
        <div className="form-row"><label>Min Experience</label><input value={minExp} onChange={(e)=>setMinExp(e.target.value)} type="number" /></div>
        <div className="form-row"><label>Max Active Tasks</label><input value={maxActive} onChange={(e)=>setMaxActive(e.target.value)} type="number" /></div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onSubmit} disabled={isLoading}>Create Task</button>
          <button onClick={onUpdate} className="secondary">Update Task</button>
          <button onClick={onDelete} className="secondary">Delete Task</button>
        </div>
        <pre className="result">{result}</pre>
      </section>
    </Layout>
  );
}

function AdminUsersPage() {
  const role = useSelector((s:any)=>s.auth.role);
  const [createUser, { isLoading }] = useCreateUserMutation();
  const [updateUser] = useUpdateUserMutation();
  const [deleteUser] = useDeleteUserMutation();
  const { data, refetch, isFetching } = useListUsersQuery();
  const [form, setForm] = React.useState({ id:"", name:"", department:"", experience_years:"", active_task_count:"0", location:"", password:"" });
  const [result, setResult] = React.useState("");
  if (role !== "ADMIN") return <Layout><section><p>Admin only</p></section></Layout>;
  async function onCreate() {
    try {
      const payload: any = {
        id: Number(form.id),
        name: form.name,
        department: form.department,
        experience_years: Number(form.experience_years),
        active_task_count: Number(form.active_task_count),
        location: form.location || null,
        ...(form.password ? { password: form.password } : {}),
      };
      const res = await createUser(payload).unwrap();
      setResult(JSON.stringify(res, null, 2));
      refetch();
    } catch {
      setResult("Error creating user");
    }
  }
  async function onUpdate() {
    try {
      const payload: any = {
        id: Number(form.id),
        name: form.name,
        department: form.department,
        experience_years: Number(form.experience_years),
        active_task_count: Number(form.active_task_count),
        location: form.location || null,
        ...(form.password ? { password: form.password } : {}),
      };
      const res = await updateUser(payload).unwrap();
      setResult(JSON.stringify(res, null, 2));
      refetch();
    } catch {
      setResult("Error updating user");
    }
  }
  async function onDelete() {
    try {
      const res = await deleteUser(Number(form.id)).unwrap();
      setResult(JSON.stringify(res, null, 2));
      refetch();
    } catch {
      setResult("Error deleting user");
    }
  }
  return (
    <Layout>
      <section>
        <h2>Users</h2>
        <div className="grid">
          <div className="panel">
            <h3>Create User (ADMIN)</h3>
            {["id","name","department","experience_years","active_task_count","location","password"].map((k)=>(
              <div className="form-row" key={k}>
                <label>{k.replaceAll("_"," ")}</label>
                <input value={(form as any)[k]} onChange={(e)=>setForm({...form,[k]:e.target.value})} type={k.includes("years")||k.includes("count")||k==="id"?"number":(k==="password"?"password":"text")} />
              </div>
            ))}
            <div style={{ display:"flex", gap: 8 }}>
              <button onClick={onCreate} disabled={isLoading}>Create/Upsert User</button>
              <button onClick={onUpdate} className="secondary">Update User</button>
              <button onClick={onDelete} className="secondary">Delete User</button>
            </div>
            <pre className="result">{result}</pre>
          </div>
          <div className="panel">
            <h3>List Users</h3>
            <button onClick={()=>refetch()} disabled={isFetching}>List Users</button>
            <pre className="result">{data ? JSON.stringify(data, null, 2) : ""}</pre>
          </div>
        </div>
      </section>
    </Layout>
  );
}

function AdminRecomputePage() {
  const role = useSelector((s:any)=>s.auth.role);
  const [recompute, { isLoading }] = useRecomputeMutation();
  const [taskId, setTaskId] = React.useState("");
  const [department, setDepartment] = React.useState("");
  const [minExp, setMinExp] = React.useState("");
  const [result, setResult] = React.useState("");
  if (role !== "ADMIN") return <Layout><section><p>Admin only</p></section></Layout>;
  async function onSubmit() {
    const body: any = {
      task_id: Number(taskId),
      rules: {
        ...(department ? { department } : {}),
        ...(minExp ? { min_experience: Number(minExp) } : {}),
      },
    };
    try {
      const res = await recompute(body).unwrap();
      setResult(JSON.stringify(res, null, 2));
    } catch {
      setResult("Error recomputing");
    }
  }
  return (
    <Layout>
      <section>
        <h2>Recompute Eligibility (ADMIN)</h2>
        <div className="form-row"><label>Task ID</label><input value={taskId} onChange={(e)=>setTaskId(e.target.value)} type="number" /></div>
        <div className="form-row"><label>Department</label><input value={department} onChange={(e)=>setDepartment(e.target.value)} /></div>
        <div className="form-row"><label>Min Experience</label><input value={minExp} onChange={(e)=>setMinExp(e.target.value)} type="number" /></div>
        <button onClick={onSubmit} disabled={isLoading}>Recompute</button>
        <pre className="result">{result}</pre>
      </section>
    </Layout>
  );
}

function AdminAssignmentsPage() {
  const role = useSelector((s:any)=>s.auth.role);
  const [taskId, setTaskId] = React.useState("");
  const [userId, setUserId] = React.useState("");
  const { data: all, refetch } = useListAssignmentsQuery();
  const { data: assnByTask, refetch: refetchByTask } = useGetAssignmentQuery(taskId ? Number(taskId) : 0, { skip: !taskId });
  const { data: assnByUser, refetch: refetchByUser } = useAssignmentsByUserQuery(userId ? Number(userId) : 0, { skip: !userId });
  const [upsert] = useUpsertAssignmentMutation();
  const [updateStatus] = useUpdateAssignmentStatusMutation();
  const [updateStatusByUid] = useUpdateAssignmentStatusByUidMutation();
  const [taskUid, setTaskUid] = React.useState("");
  const [result, setResult] = React.useState("");
  if (role !== "ADMIN") return <Layout><section><p>Admin only</p></section></Layout>;
  async function onUpsert() {
    try {
      const res = await upsert({ task_id: Number(taskId), user_id: Number(userId) }).unwrap();
      setResult(JSON.stringify(res, null, 2));
      refetch();
      refetchByTask();
      refetchByUser();
    } catch {
      setResult("Error upserting assignment");
    }
  }
  return (
    <Layout>
      <section>
        <h2>Assignments (ADMIN)</h2>
        <div className="grid">
          <div className="panel">
            <h3>Upsert Assignment</h3>
            <div className="form-row"><label>Task ID</label><input value={taskId} onChange={(e)=>setTaskId(e.target.value)} type="number" /></div>
            <div className="form-row"><label>User ID</label><input value={userId} onChange={(e)=>setUserId(e.target.value)} type="number" /></div>
            <button onClick={onUpsert}>Assign/Reassign</button>
            <pre className="result">{result}</pre>
          </div>
          <div className="panel">
            <h3>List All</h3>
            <button onClick={()=>refetch()}>List Assignments</button>
            <pre className="result">{all ? JSON.stringify(all, null, 2) : ""}</pre>
          </div>
          <div className="panel">
            <h3>By Task</h3>
            <button onClick={()=>refetchByTask()} disabled={!taskId}>Get By Task</button>
            <pre className="result">{assnByTask ? JSON.stringify(assnByTask, null, 2) : ""}</pre>
            <div style={{ display:"flex", gap:8 }}>
              <button onClick={async()=>{ if (!taskId) return; const r=await updateStatus({ task_id:Number(taskId), status:"COMPLETED" }).unwrap(); setResult(JSON.stringify(r,null,2)); refetch(); refetchByTask(); refetchByUser(); }}>Mark Completed</button>
              <button onClick={async()=>{ if (!taskId) return; const r=await updateStatus({ task_id:Number(taskId), status:"CANCELLED" }).unwrap(); setResult(JSON.stringify(r,null,2)); refetch(); refetchByTask(); refetchByUser(); }} className="secondary">Mark Cancelled</button>
            </div>
            <div className="form-row"><label>Task UID</label><input value={taskUid} onChange={(e)=>setTaskUid(e.target.value)} /></div>
            <div style={{ display:"flex", gap:8 }}>
              <button onClick={async()=>{ if (!taskUid) return; const r=await updateStatusByUid({ task_uid:taskUid, status:"COMPLETED" }).unwrap(); setResult(JSON.stringify(r,null,2)); refetch(); refetchByTask(); refetchByUser(); }}>Mark Completed by UID</button>
              <button onClick={async()=>{ if (!taskUid) return; const r=await updateStatusByUid({ task_uid:taskUid, status:"CANCELLED" }).unwrap(); setResult(JSON.stringify(r,null,2)); refetch(); refetchByTask(); refetchByUser(); }} className="secondary">Mark Cancelled by UID</button>
            </div>
          </div>
          <div className="panel">
            <h3>By User</h3>
            <button onClick={()=>refetchByUser()} disabled={!userId}>Get By User</button>
            <pre className="result">{assnByUser ? JSON.stringify(assnByUser, null, 2) : ""}</pre>
          </div>
        </div>
      </section>
    </Layout>
  );
}

const router = createBrowserRouter([
  { path: "/", element: <LoginPage /> },
  { path: "/tasks", element: <TasksPage /> },
  { path: "/eligible", element: <EligiblePage /> },
  { path: "/my-tasks", element: <MyTasksPage /> },
  { path: "/admin/create-task", element: <AdminCreateTaskPage /> },
  { path: "/admin/users", element: <AdminUsersPage /> },
  { path: "/admin/recompute", element: <AdminRecomputePage /> },
  { path: "/admin/assignments", element: <AdminAssignmentsPage /> },
]);

async function bootstrap() {
  try {
    const res = await fetch("http://localhost:8000/env", { method: "GET" });
    if (res.ok) {
      const data = await res.json();
      (window as any).GATEWAY_BASE = data.gateway_base;
    }
  } catch {
    (window as any).GATEWAY_BASE = (window as any).GATEWAY_BASE || "http://localhost:8000";
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>
    </React.StrictMode>
  );
}

bootstrap();
