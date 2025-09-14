import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [complaints, setComplaints] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchComplaints = async () => {
    try {
      const response = await fetch('http://localhost:8000/complaints');
      const data = await response.json();
      setComplaints(data.complaints);
      setLoading(false);
    } catch (error) {
      console.error('Ошибка загрузки:', error);
      setLoading(false);
    }
  };

  const markAsProcessed = async (id) => {
    try {
      await fetch(`http://localhost:8000/complaint/${id}/processed`, { method: 'POST' });
      fetchComplaints();
    } catch (error) {
      console.error('Ошибка отметки:', error);
    }
  };

  useEffect(() => {
    fetchComplaints();
  }, []);

  if (loading) return <p>Загрузка...</p>;

  return (
    <div className="App">
      <h1>Жалобы ЖКХ</h1>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Текст</th>
            <th>Адрес</th>
            <th>Категория</th>
            <th>Время ЧП</th>
            <th>Создано</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          {complaints.map((complaint) => (
            <tr key={complaint.id}>
              <td>{complaint.id}</td>
              <td>{complaint.text}</td>
              <td>{complaint.address}</td>
              <td>{complaint.category}</td>
              <td>{complaint.incident_time}</td>
              <td>{complaint.created_at}</td>
              <td>
                <button onClick={() => markAsProcessed(complaint.id)}>Отметить выполненной</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {complaints.length === 0 && <p>Нет новых жалоб.</p>}
    </div>
  );
}

export default App;